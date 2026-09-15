"""One observed stall switch for disposable wild-battle qualification.

This disclosed maintenance policy is opt-in. It uses the existing semantic
reserve ranking, never a route/species recipe, and makes no survival prediction.
A MAIN observation with no HP decrease is not evidence of an immunity or miss.
No-progress thresholds are resource heuristics, not learned battle authority.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .battle_recovery import EmulatorState, switch_active_battler
from .battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    BattleActionExecutor,
    BattleRuntimeError,
    BattleRuntimeTiming,
    MoveSlotPolicy,
    battle_policy_override_active,
    run_adaptive_wild_battle,
)
from .battle_runtime_diagnostics import trace_phase
from .observation import BattleMenuPhase, PokemonRedStateReader, RawGameState
from .red_party import party_observation_from_raw
from .red_trainer_party import trainer_matchup_candidates

LEGACY_POLICY = "fixed_strongest_usable_move"
CONTINGENCY_POLICY = "fixed_strongest_usable_move_with_stall_switch_v1"
STALL_TURN_LIMIT = 4
MAXIMUM_SWITCHES = 1


class BattleContingencyError(BattleRuntimeError):
    """A bounded maintenance contingency cannot continue."""


@dataclass(slots=True)
class RedBattleContingency:
    reader: PokemonRedStateReader
    emulator: EmulatorState
    executor: BattleActionExecutor
    record: Callable[[dict[str, object]], None]
    stalled_turns: int = field(default=0, init=False)
    switches_claimed: int = field(default=0, init=False)
    switches_completed: int = field(default=0, init=False)
    _previous: tuple[RawGameState, int] | None = field(default=None, init=False)
    _origin: RawGameState | None = field(default=None, init=False)
    _claimed: bool = field(default=False, init=False)

    def run(
        self, move_policy: MoveSlotPolicy, *, expected_map: int,
        timing: BattleRuntimeTiming = DEFAULT_BATTLE_RUNTIME_TIMING,
        label: str = "bounded wild battle contingency",
    ) -> RawGameState:
        if self._claimed:
            raise BattleContingencyError("contingency controller already consumed")
        self._claimed = True
        if battle_policy_override_active():
            raise BattleContingencyError("contingency cannot override a learned actor")
        return run_adaptive_wild_battle(
            self.reader, self.executor, move_policy, expected_map=expected_map,
            timing=timing, label=label, move_decision_sink=self._selected,
            main_menu_intervention=self._intervene,
        )

    def _selected(self, raw: RawGameState, slot: int) -> None:
        # Called only after the shared runtime has validated the move selection.
        self._previous = (raw, slot)

    def _intervene(self, raw: RawGameState) -> bool:
        self._require_boundary(raw)
        if self._origin is None:
            self._origin = raw
        self._require_encounter(raw)
        if self._previous is not None:
            before, slot = self._previous
            if (raw.active_party_index != before.active_party_index
                    or raw.battler_moves != before.battler_moves):
                raise BattleContingencyError("unqualified battler or move replacement")
            assert before.battler_pp is not None and raw.battler_pp is not None
            old = tuple(pp & 63 for pp in before.battler_pp)
            current = tuple(pp & 63 for pp in raw.battler_pp)
            spent = tuple(pp - (i == slot - 1) for i, pp in enumerate(old))
            if current not in (old, spent):
                raise BattleContingencyError("unqualified PP transition between MAIN turns")
            assert raw.enemy_hp is not None and before.enemy_hp is not None
            if raw.enemy_hp < before.enemy_hp:
                self.stalled_turns = 0
            elif current == spent:
                self.stalled_turns += 1
            self._previous = None
        reason = (
            "no_usable_pp" if not _has_usable_move(raw)
            else "no_hp_progress" if self.stalled_turns >= STALL_TURN_LIMIT else None
        )
        if reason is None:
            return False
        self.record({
            "event": "contingency_needed", "reason": reason,
            "stalled_turns": self.stalled_turns, "active_party_index": raw.active_party_index,
            "enemy_hp": raw.enemy_hp, "pp": list(raw.battler_pp or ()),
        })
        if self.switches_claimed >= MAXIMUM_SWITCHES:
            raise BattleContingencyError("contingency switch budget exhausted")
        target = _reserve(raw)
        self.switches_claimed += 1  # Claim before persistence/input; failure never refunds it.
        self.record({"event": "switch_claimed", "reason": reason, "target_index": target})
        trace_phase("contingency_switch")
        if self.reader.read() != raw:
            raise BattleContingencyError("contingency switch state changed before input")
        if self.reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN:
            raise BattleContingencyError("contingency switch lost MAIN before input")
        switch_active_battler(
            self.executor, self.reader, self.emulator, target,
            expected_battle_state=1, label="observed stall contingency", wait_frames=180,
        )
        after = self.reader.read()
        self._require_boundary(after)
        self._require_encounter(after)
        if after.active_party_index != target or after.bag_items != raw.bag_items:
            raise BattleContingencyError("contingency switch result differs")
        if self.reader.read_battle_menu_state(after).phase is not BattleMenuPhase.MAIN:
            raise BattleContingencyError("contingency switch did not settle at MAIN")
        self.switches_completed += 1
        self.stalled_turns = 0
        self.record({"event": "switch_completed", "target_index": target,
                     "hp_after": after.battler_hp, "enemy_hp_after": after.enemy_hp})
        return True

    def _require_encounter(self, raw: RawGameState) -> None:
        origin = self._origin
        assert origin is not None
        # Identity is used only to reject an encounter change, never to rank actions.
        if (raw.map_id, raw.enemy_species_id, raw.enemy_level, raw.enemy_max_hp) != (
            origin.map_id, origin.enemy_species_id, origin.enemy_level, origin.enemy_max_hp,
        ):
            raise BattleContingencyError("contingency encounter changed")
        if raw.bag_items != origin.bag_items:
            raise BattleContingencyError("contingency cannot spend items")

    @staticmethod
    def _require_boundary(raw: RawGameState) -> None:
        index = raw.active_party_index
        if (raw.battle_state != 1 or type(index) is not int
                or raw.party_hp is None or not 0 <= index < len(raw.party_hp)
                or type(raw.active_party_hp) is not int or raw.active_party_hp <= 0
                or raw.party_hp[index] <= 0 or raw.enemy_hp is None or raw.enemy_hp <= 0
                or raw.active_party_moves is None or len(raw.active_party_moves) != 4
                or raw.active_party_pp is None or len(raw.active_party_pp) != 4
                or any(type(move) is not int or not 0 <= move <= 165
                       for move in raw.active_party_moves)
                or any(type(pp) is not int or not 0 <= pp <= 255
                       for pp in raw.active_party_pp)):
            raise BattleContingencyError("contingency requires a living observed wild MAIN turn")


def _has_usable_move(raw: RawGameState) -> bool:
    return any(
        move and (pp & 63) > 0 and not (
            raw.player_disabled_move_slot == i + 1 and (raw.player_disable_turns or 0) > 0
        )
        for i, (move, pp) in enumerate(zip(
            raw.battler_moves or (), raw.battler_pp or (), strict=True,
        ))
    )


def _reserve(raw: RawGameState) -> int:
    if raw.enemy_species_id is None or raw.enemy_level is None:
        raise BattleContingencyError("reserve matchup observation unavailable")
    # Reuse shared scalar matchup ranking. Its half-HP/healthy/level screen and
    # ordinary non-immune move requirement are heuristics, not entry survival proof.
    candidates = trainer_matchup_candidates(
        party_observation_from_raw(raw), opponent_species=raw.enemy_species_id,
        opponent_level=raw.enemy_level,
    )
    target = next((c.party_slot - 1 for c in candidates
                   if c.party_slot - 1 != raw.active_party_index), None)
    if target is None:
        raise BattleContingencyError("no eligible offensive reserve")
    return target
