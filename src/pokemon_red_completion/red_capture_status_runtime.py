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
from pokemon_red_completion.observation import (
    PokemonRedStateReader,
    RawGameState,
    WildCaptureIdentity,
)
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
    throw_preparations: list[dict[str, object]] = field(default_factory=list, init=False)
    bypassed_for_escape: bool = field(default=False, init=False)
    latched_original_species_id: int | None = field(default=None, init=False)

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
        identity = self.reader.read_wild_capture_identity()
        if identity is None:
            raise RedCaptureStatusError("capture preparation lacks a live target")
        if self.latched_original_species_id is None:
            self.latched_original_species_id = identity.original_species_id
        elif identity.original_species_id != self.latched_original_species_id:
            raise RedCaptureStatusError("capture status changed target, party or bag")

        target_hp = initial.enemy_hp
        party_ids = initial.party_species_ids
        initial_bag = initial.bag_items
        if target_hp is None or target_hp <= 0 or initial.map_id is None:
            raise RedCaptureStatusError("capture preparation lacks a live target")
        self._require_protected(initial, identity, target_hp, party_ids, initial_bag)
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
            identity = self.reader.read_wild_capture_identity()
            self._require_protected(self.reader.read(), identity, target_hp, party_ids, initial_bag)
            self.bypassed_for_escape = True
            return self._record_throw_preparation()
        for _ in range(self.maximum_attempts - self.attempts):
            raw = self.reader.read()
            if raw.battle_state != 1:
                return False
            identity = self.reader.read_wild_capture_identity()
            self._require_protected(raw, identity, target_hp, party_ids, initial_bag)
            assert identity is not None
            # Transform can also happen in reply to a status move, not only a
            # switch. Recheck before each additional setup turn.
            current_moves = self.reader.read_enemy_capture_moves()
            if current_moves is None:
                raise RedCaptureStatusError("capture target moves are unavailable")
            if any(RED_BATTLE_CATALOG.can_end_wild_encounter(pokemon_red_move_ref(move))
                   for move in current_moves if move):
                self.bypassed_for_escape = True
                return self._record_throw_preparation()
            status_byte = self.reader.read_enemy_capture_status()
            if status_byte is None:
                raise RedCaptureStatusError("capture target status is unavailable")
            party = PokemonRedPartyReader(self.emulator).read()
            option = choose_capture_status(
                party,
                red_capture_status_options(
                    party,
                    enemy_species_id=identity.displayed_species_id,
                    live_type_names=identity.type_names,
                ),
                target_status=decode_status(status_byte),
                attempts_used=self.attempts,
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
                identity = self.reader.read_wild_capture_identity()
                self._require_protected(raw, identity, target_hp, party_ids, initial_bag)
                assert identity is not None
                helper = PokemonRedPartyReader(self.emulator).read().members[option.party_slot - 1]
                if helper.hp_ratio <= 0.5 or helper.status is not StatusCondition.HEALTHY:
                    break
                # Recheck live types and escape moves after a switch so newly
                # transformed types do not use stale immunity or risk escape.
                post_moves = self.reader.read_enemy_capture_moves()
                if post_moves is None:
                    raise RedCaptureStatusError("capture target moves are unavailable")
                if any(RED_BATTLE_CATALOG.can_end_wild_encounter(pokemon_red_move_ref(move))
                       for move in post_moves if move):
                    self.bypassed_for_escape = True
                    return self._record_throw_preparation()
                post_status_byte = self.reader.read_enemy_capture_status()
                if post_status_byte is None:
                    raise RedCaptureStatusError("capture target status is unavailable")
                current_status = decode_status(post_status_byte)
                if current_status is not StatusCondition.HEALTHY:
                    break
                party = PokemonRedPartyReader(self.emulator).read()
                live_options = red_capture_status_options(
                    party,
                    enemy_species_id=identity.displayed_species_id,
                    live_type_names=identity.type_names,
                )
                option = choose_capture_status(
                    party,
                    live_options,
                    target_status=current_status,
                    attempts_used=self.attempts,
                    maximum_attempts=self.maximum_attempts,
                    active_party_slot=(
                        raw.active_party_index + 1 if raw.active_party_index is not None else None
                    ),
                )
                if option is None or option.party_slot - 1 != raw.active_party_index:
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
            identity = self.reader.read_wild_capture_identity()
            self._require_protected(after, identity, target_hp, party_ids, initial_bag)
            if (after.battler_hp or 0) <= 0:
                raise RedCaptureStatusError("capture status helper fainted; stop safely")
            advance_battle_to_policy_boundary(
                self.reader, self.actions, expected_map=initial.map_id,
                expected_battle_state=1, label="capture status turn settlement",
            )
            after = self.reader.read()
            identity = self.reader.read_wild_capture_identity()
            self._require_protected(after, identity, target_hp, party_ids, initial_bag)
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
            assert identity is not None
            self.reports.append({
                "attempt": self.attempts, "party_slot": option.party_slot,
                "move_slot": option.move_slot, "condition": option.condition.value,
                "move_executed": turn.move_executed, "status_after": actual.value,
                "status_success": actual is option.condition,
                "target_hp_before": target_hp, "target_hp_after": after.enemy_hp,
                "target_preserved": True, "balls_spent": 0,
                "original_species_id": identity.original_species_id,
                "displayed_species_id": identity.displayed_species_id,
                "transformed": identity.transformed,
            })
        current = self.reader.read()
        if current.battle_state != 1:
            return False
        identity = self.reader.read_wild_capture_identity()
        self._require_protected(current, identity, target_hp, party_ids, initial_bag)
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
                self.reader.read(), self.reader.read_wild_capture_identity(),
                target_hp, party_ids, initial_bag,
            )
        return self._record_throw_preparation()

    def _record_throw_preparation(self) -> bool:
        """Observe after setup/switching; this does not claim an executed throw.

        Status-attempt reports describe the earlier move result. In particular,
        sleep may expire during a protective switch. Keep the later observation
        separate so diagnostics cannot inflate attempted or successful moves.
        No controller action, prediction, reward or policy feature is added.
        """
        raw = self.reader.read()
        status = self.reader.read_enemy_capture_status()
        identity = self.reader.read_wild_capture_identity()
        self.throw_preparations.append({
            "preparation_ordinal": len(self.throw_preparations) + 1,
            "status_attempts_used": self.attempts,
            "target_status": decode_status(status).value if status is not None else None,
            "target_hp": raw.enemy_hp,
            "target_max_hp": raw.enemy_max_hp,
            "active_party_slot": (
                raw.active_party_index + 1 if raw.active_party_index is not None else None
            ),
            "original_species_id": identity.original_species_id if identity else None,
            "displayed_species_id": identity.displayed_species_id if identity else None,
            "transformed": identity.transformed if identity else None,
            "escape_setup_bypassed": self.bypassed_for_escape,
            "throw_executed": False,
        })
        return True

    def _require_protected(
        self,
        raw: RawGameState,
        identity: WildCaptureIdentity | None,
        hp: int,
        party_ids: tuple[int, ...] | None,
        bag: tuple[tuple[int, int], ...] | None,
    ) -> None:
        if (
            raw.battle_state != 1
            or raw.enemy_hp != hp
            or raw.party_species_ids != party_ids
            or raw.bag_items != bag
        ):
            raise RedCaptureStatusError("capture status changed target, party or bag")
        if identity is None:
            raise RedCaptureStatusError("capture status lacks a live target")
        if (
            self.latched_original_species_id is not None
            and identity.original_species_id != self.latched_original_species_id
        ):
            raise RedCaptureStatusError("capture status changed target, party or bag")
        if not identity.transformed and raw.enemy_species_id != identity.original_species_id:
            raise RedCaptureStatusError("capture status changed target, party or bag")
        if identity.transformed and raw.enemy_species_id != identity.displayed_species_id:
            raise RedCaptureStatusError("capture status changed target, party or bag")
