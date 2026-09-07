"""Opt-in status preparation reusing the shared switch and one-turn executors.

All status success is observed. The callback owns a finite per-encounter budget;
it never selects a damaging move or counts a wild exit as a capture.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pokemon_red_completion.battle_recovery import (
    EmulatorState,
    ProtectedRecoveryError,
    switch_active_battler,
)
from pokemon_red_completion.battle_runtime import (
    advance_battle_to_policy_boundary,
    execute_bounded_battle_move_turn,
)
from pokemon_red_completion.capture_support import choose_capture_status
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import PokemonRedStateReader, RawGameState
from pokemon_red_completion.party import StatusCondition
from pokemon_red_completion.red_capture_support import red_capture_status_options
from pokemon_red_completion.red_party import PokemonRedPartyReader, decode_status


class RedCaptureStatusError(RuntimeError):
    """An observed status turn changed protected capture state."""


@dataclass(slots=True)
class RedCaptureStatusPreparer:
    emulator: EmulatorState
    actions: CountingExecutor
    reader: PokemonRedStateReader
    maximum_attempts: int = 3
    attempts: int = field(default=0, init=False)
    reports: list[dict[str, object]] = field(default_factory=list, init=False)
    bypassed_for_escape: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if type(self.maximum_attempts) is not int or not 1 <= self.maximum_attempts <= 10:
            raise ValueError("capture preparation attempt bound differs")

    def __call__(self) -> bool:
        """Return False only if the encounter ended; True permits a ball.

        A True result does not assert the opponent is statused. Reports retain
        actual status, PP and HP proof for every attempted move.
        """
        initial = self.reader.read()
        if initial.battle_state != 1:
            return False
        target = initial.enemy_species_id
        target_hp = initial.enemy_hp
        party_ids = initial.party_species_ids
        initial_bag = initial.bag_items
        if target is None or target_hp is None or target_hp <= 0 or initial.map_id is None:
            raise RedCaptureStatusError("capture preparation lacks a live target")
        advance_battle_to_policy_boundary(
            self.reader, self.actions, expected_map=initial.map_id,
            expected_battle_state=1, label="capture status introduction",
        )
        from pokemon_red_completion.red_battle_catalog import (
            RED_BATTLE_CATALOG,
            pokemon_red_move_ref,
        )

        moves = self.reader.read_enemy_capture_moves()
        if moves is None:
            raise RedCaptureStatusError("capture target moves are unavailable")
        if any(RED_BATTLE_CATALOG.can_end_wild_encounter(pokemon_red_move_ref(move))
               for move in moves if move):
            # A setup/switch turn may lose the encounter before any ball. Keep
            # the current battler and permit the ball; do not invent sleep or
            # assume the opponent's move choice, speed or escape outcome.
            self._require_protected(self.reader.read(), target, target_hp, party_ids, initial_bag)
            self.bypassed_for_escape = True
            return True
        for _ in range(self.maximum_attempts - self.attempts):
            raw = self.reader.read()
            if raw.battle_state != 1:
                return False
            self._require_protected(raw, target, target_hp, party_ids, initial_bag)
            status_byte = self.reader.read_enemy_capture_status()
            if status_byte is None:
                raise RedCaptureStatusError("capture target status is unavailable")
            party = PokemonRedPartyReader(self.emulator).read()
            option = choose_capture_status(
                party, red_capture_status_options(party, enemy_species_id=target),
                target_status=decode_status(status_byte), attempts_used=self.attempts,
                maximum_attempts=self.maximum_attempts,
                active_party_slot=(
                    raw.active_party_index + 1 if raw.active_party_index is not None else None
                ),
            )
            if option is None:
                break
            if raw.active_party_index != option.party_slot - 1:
                try:
                    switch_active_battler(
                        self.actions, self.reader, self.emulator, option.party_slot - 1,
                        expected_battle_state=1, label="capture status helper", wait_frames=120,
                    )
                except ProtectedRecoveryError:
                    if self.reader.read().battle_state == 0:
                        return False
                    raise
                raw = self.reader.read()
                self._require_protected(raw, target, target_hp, party_ids, initial_bag)
                helper = PokemonRedPartyReader(self.emulator).read().members[option.party_slot - 1]
                if helper.hp_ratio <= 0.5 or helper.status is not StatusCondition.HEALTHY:
                    break
            before_pp = PokemonRedPartyReader(self.emulator).read().members[
                option.party_slot - 1
            ].moves[option.move_slot - 1].current_pp
            self.attempts += 1
            turn = execute_bounded_battle_move_turn(
                self.reader, self.actions, expected_map=initial.map_id,
                selected_slot=option.move_slot, expected_battle_state=1,
                label="non-damaging capture status",
            )
            after = self.reader.read()
            if after.battle_state == 0:
                self.reports.append({"attempt": self.attempts, "encounter_ended": True,
                                     "status_success": False})
                return False
            self._require_protected(after, target, target_hp, party_ids, initial_bag)
            if (after.battler_hp or 0) <= 0:
                raise RedCaptureStatusError("capture status helper fainted; stop safely")
            advance_battle_to_policy_boundary(
                self.reader, self.actions, expected_map=initial.map_id,
                expected_battle_state=1, label="capture status turn settlement",
            )
            after = self.reader.read()
            self._require_protected(after, target, target_hp, party_ids, initial_bag)
            after_pp = PokemonRedPartyReader(self.emulator).read().members[
                option.party_slot - 1
            ].moves[option.move_slot - 1].current_pp
            if before_pp - after_pp != int(turn.move_executed):
                raise RedCaptureStatusError("capture status move PP differs")
            after_byte = self.reader.read_enemy_capture_status()
            if after_byte is None:
                raise RedCaptureStatusError("capture status outcome is unavailable")
            actual = decode_status(after_byte)
            if actual not in {StatusCondition.HEALTHY, option.condition}:
                raise RedCaptureStatusError("capture status effect differs from selected move")
            self.reports.append({
                "attempt": self.attempts, "party_slot": option.party_slot,
                "move_slot": option.move_slot, "condition": option.condition.value,
                "move_executed": turn.move_executed, "status_after": actual.value,
                "status_success": actual is option.condition,
                "target_hp_before": target_hp, "target_hp_after": after.enemy_hp,
                "target_preserved": True, "balls_spent": 0,
            })
        current = self.reader.read()
        if current.battle_state != 1:
            return False
        self._require_protected(current, target, target_hp, party_ids, initial_bag)
        healthy = [
            member for member in PokemonRedPartyReader(self.emulator).read().members
            if member.hp_ratio > 0.5 and member.status is StatusCondition.HEALTHY
        ]
        if not healthy:
            raise RedCaptureStatusError("capture preparation has no healthy catcher")
        # The low-level status helper is not left to absorb repeated failed-ball
        # turns. Switching can consume sleep turns; do not claim status persists.
        catcher = max(healthy, key=lambda member: (member.hp, member.level))
        if current.active_party_index != catcher.slot - 1:
            switch_active_battler(
                self.actions, self.reader, self.emulator, catcher.slot - 1,
                expected_battle_state=1, label="capture protected catcher", wait_frames=120,
            )
            self._require_protected(
                self.reader.read(), target, target_hp, party_ids, initial_bag,
            )
        return True

    @staticmethod
    def _require_protected(
        raw: RawGameState,
        target: int,
        hp: int,
        party_ids: tuple[int, ...] | None,
        bag: tuple[tuple[int, int], ...] | None,
    ) -> None:
        if (
            raw.battle_state != 1 or raw.enemy_species_id != target or raw.enemy_hp != hp
            or raw.party_species_ids != party_ids or raw.bag_items != bag
        ):
            raise RedCaptureStatusError("capture status changed target, party or bag")
