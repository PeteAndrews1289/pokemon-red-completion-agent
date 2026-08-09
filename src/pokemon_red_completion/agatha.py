"""Qualified Agatha chapter for the pinned Pokémon Red runtime."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_actions import (
    BattleAction,
    BattleBoostStat,
    BattleControlRequest,
    control_request_matches,
    recovery_request_matches,
    switch_request_party_index,
)
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_recovery import (
    ProtectedRecoveryError,
    switch_active_battler,
)
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRecoveryCapability,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    BattleSwitchCapability,
    note_observed_trainer_battle_exit,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.blaine import _select_cursor
from pokemon_red_completion.celadon import (
    _bag,
    _party_hp,
    _party_max_hp,
    _party_status,
)
from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
from pokemon_red_completion.field_recovery import plan_party_recovery, use_field_recovery_item
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _close_menus,
    _open_bag,
    _select_bag_item,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.participation import summarize_party_participation
from pokemon_red_completion.red_battle_catalog import (
    RED_BATTLE_CATALOG,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from pokemon_red_completion.red_party import (
    DUGTRIO_SPECIES_ID,
    DUX_SPECIES_ID,
    JOLTEON_SPECIES_ID,
)
from pokemon_red_completion.silph import (
    DEFAULT_SILPH_TIMING,
    SilphChapterError,
    _battle_healing_item,
)
from pokemon_red_completion.tower import party_core_intact
from pokemon_red_completion.victory_road import (
    INDIGO_X_SPECIAL_RESERVE,
    _event,
    _menu_cursor_active,
    _move,
    _pulse,
    _select_battle_main_command,
    _settle_confirm,
)

AGATHA_CHECKPOINT_COUNT = 3
AGATHA_RNG_DELAY_FRAMES = 85
AGATHA_PARTY = (
    (0x0E, 56),
    (0x82, 56),
    (0x93, 55),
    (0x2D, 58),
    (0x0E, 60),
)
AGATHA_APPROACH = ("right", "up", "up")
# Surf and Ice Beam are the only attacks in the League set that can damage
# Agatha's Ghost-types.  Preserve a single Surf for Lance's Aerodactyl and
# spend the rest here so Ice Beam remains available for Lance's dragons.
AGATHA_SURF_RESERVE = 1
AGATHA_X_SPECIAL_USE = 1
AGATHA_ELIXIR_USE = 1
AGATHA_FORCED_SWITCH_LIMIT = 5
AGATHA_RESERVE_SAFE_HP = 60
AGATHA_DUGTRIO_TARGET_POSITIONS = frozenset({0, 2, 3, 4})
AGATHA_JOLTEON_TARGET_POSITIONS = frozenset({1})
EARTHQUAKE_MOVE_ID = 0x59
THUNDER_MOVE_ID = 0x57
THUNDER_SHOCK_MOVE_ID = 0x54


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class AgathaChapterError(RuntimeError):
    """Raised when the Agatha evidence contract fails."""


@dataclass(frozen=True, slots=True)
class AgathaProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[AgathaProgress], None]


@dataclass(frozen=True, slots=True)
class AgathaCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class AgathaTurn:
    species: int
    level: int
    enemy_hp: int
    lead_hp: int
    lead_status: int
    pp: tuple[int, int, int, int]
    move_slot: int
    party_position: int = 0
    active_party_index: int | None = None
    active_party_species_id: int | None = None


@dataclass(frozen=True, slots=True)
class AgathaChapterReport:
    records: tuple[AgathaCheckpoint, ...]
    final_raw: RawGameState
    turns: tuple[AgathaTurn, ...]
    party: tuple[tuple[int, int], ...]
    hyper_potions_used: int
    full_restores_used: int
    x_specials_used: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool
    team_switches: int

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == AGATHA_CHECKPOINT_COUNT
            and self.party == _encounter_party(self.turns)
            and _observed_party_valid(self.turns)
            and _turns_valid(self.turns)
            and self.x_specials_used == AGATHA_X_SPECIAL_USE
            and _event(self.final_raw, EventFlag.BEAT_AGATHA)
            and self.final_raw.map_id == MapId.LANCES_ROOM
            and party_core_intact(self.final_raw.party_species_ids)
            and self.party_hp == self.party_max_hp
            and all(status == 0 for status in self.party_status)
            and _agatha_team_lesson_satisfied(self.turns)
            and self.team_switches == 3
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        participation = summarize_party_participation(
            (turn.active_party_index for turn in self.turns),
            party_size=len(self.party_hp),
        )
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "defeat_agatha",
            "source_party": [list(item) for item in AGATHA_PARTY],
            # Gen I trainers may switch a fresh party member into an attack that
            # was selected against another opponent.  Such a member can faint
            # before the teacher receives another decision boundary, so keep
            # the policy-visible subset distinct from the declared roster.
            "party": [list(item) for item in self.party],
            "turns": [
                {
                    "species": item.species,
                    "level": item.level,
                    "enemy_hp": item.enemy_hp,
                    "lead_hp": item.lead_hp,
                    "lead_status": item.lead_status,
                    "pp": list(item.pp),
                    "move_slot": item.move_slot,
                    "party_position": item.party_position,
                    "active_party_index": item.active_party_index,
                    "active_party_species_id": item.active_party_species_id,
                }
                for item in self.turns
            ],
            "participation": participation.public_dict(),
            "team_switches": self.team_switches,
            "recovery": {
                "hyper_potions_used": self.hyper_potions_used,
                "full_restores_used": self.full_restores_used,
                "x_specials_used": self.x_specials_used,
            },
            "terminal": {
                "map": int(self.final_raw.map_id),
                "position": [self.final_raw.player_x, self.final_raw.player_y],
                "party_hp": list(self.party_hp),
                "party_max_hp": list(self.party_max_hp),
                "party_status": list(self.party_status),
                "moves": list(self.final_raw.first_party_moves or ()),
                "pp": list(self.final_raw.first_party_pp or ()),
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


def run_agatha_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> AgathaChapterReport:
    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[AgathaCheckpoint] = []
    initial = reader.read()
    if (
        initial.map_id != MapId.AGATHAS_ROOM
        or (initial.player_x, initial.player_y) != (4, 5)
        or not party_core_intact(initial.party_species_ids)
        or not _event(initial, EventFlag.BEAT_BRUNO)
        or _event(initial, EventFlag.BEAT_AGATHA)
        or _bag(emulator).get(ItemId.X_SPECIAL, 0) != INDIGO_X_SPECIAL_RESERVE
    ):
        raise AgathaChapterError("Agatha input boundary is not qualified.")
    _checkpoint(records, progress, emulator, initial, "agatha_ready", "Agatha room ready")
    _use_field_elixir(actions, reader, emulator)
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=AGATHA_RNG_DELAY_FRAMES))

    _move(actions, reader, AGATHA_APPROACH, "Agatha approach")
    _pulse(actions, MacroActionKind.INTERACT)
    for _ in range(40):
        if reader.read().battle_state == 2:
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise AgathaChapterError("Agatha battle did not start.")
    _checkpoint(records, progress, emulator, reader.read(), "agatha_engaged", "Engaged Agatha")

    turns: list[AgathaTurn] = []

    class _HealBoundary(BattleControlRequest):
        default_action = BattleAction.recovery()

    class _BoostBoundary(BattleControlRequest):
        default_action = BattleAction.boost(BattleBoostStat.SPECIAL)

    class _TeamSwitchBoundary(BattleControlRequest):
        pass

    boosts_used = 0
    forced_switches = 0
    team_switches = 0

    def policy(raw: RawGameState) -> int:
        target_species = _agatha_matchup_species(raw)
        target = _agatha_matchup_switch_target(raw, target_species)
        if target is not None:
            raise _TeamSwitchBoundary(BattleAction.switch(target + 1))
        if raw.active_party_species_id != target_species:
            opponent = (
                raw.enemy_species_id,
                emulator.read_u8(RamAddress.ENEMY_MON_PARTY_POS),
            )
            raise AgathaChapterError(
                "Agatha lacks its planned matchup specialist: "
                f"enemy={opponent!r}, "
                f"wanted={target_species}, active={raw.active_party_species_id}."
            )
        if boosts_used < AGATHA_X_SPECIAL_USE and target_species == JOLTEON_SPECIES_ID:
            raise _BoostBoundary
        if _agatha_recovery_due(raw):
            raise _HealBoundary
        return _agatha_move_slot(raw)

    def record_turn(raw: RawGameState, slot: int) -> None:
        turns.append(
            AgathaTurn(
                raw.enemy_species_id or 0,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                raw.battler_hp or 0,
                raw.battler_status or 0,
                raw.battler_pp or (0, 0, 0, 0),
                slot,
                emulator.read_u8(RamAddress.ENEMY_MON_PARTY_POS),
                raw.active_party_index,
                raw.active_party_species_id,
            )
        )

    hyper_before = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    restore_before = _bag(emulator).get(ItemId.FULL_RESTORE, 0)
    x_special_before = _bag(emulator).get(ItemId.X_SPECIAL, 0)
    battle_intent = BattleIntent(
        "defeat_agatha",
        battle_plan_id=RedBattlePlanId.LEAGUE_AGATHA,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
        recovery_capabilities=frozenset(
            {
                BattleRecoveryCapability.RESTORE_HP,
                BattleRecoveryCapability.CURE_ANY_STATUS,
            }
        ),
        boost_capabilities=frozenset({BattleBoostStat.SPECIAL}),
        switch_capabilities=frozenset({BattleSwitchCapability.TEMPORARY_ROLE_PIVOT}),
    )
    while reader.read().battle_state:
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                policy,
                expected_map=MapId.AGATHAS_ROOM,
                intent=battle_intent,
                timing=BattleRuntimeTiming(
                    max_runtime_pulses=2000,
                    max_sleep_recovery_pulses=96,
                    max_post_attack_transition_pulses=30,
                ),
                label="Agatha",
                move_decision_sink=record_turn,
            )
        except BattleRuntimeError as error:
            cause = error.__cause__
            switch_target = switch_request_party_index(cause, _TeamSwitchBoundary)
            if isinstance(cause, _TeamSwitchBoundary) or switch_target is not None:
                if switch_target is None:
                    raise AgathaChapterError("Agatha team switch lacked a party target.") from error
                try:
                    switch_active_battler(
                        actions,
                        reader,
                        emulator,
                        switch_target,
                        label="Agatha matchup-aware participation",
                        wait_frames=DEFAULT_SILPH_TIMING.menu_frames,
                    )
                except ProtectedRecoveryError as switch_error:
                    raise AgathaChapterError(
                        f"Agatha matchup-aware switch failed: {switch_error}"
                    ) from switch_error
                team_switches += 1
                continue
            current = reader.read()
            if (
                current.battle_state == 2
                and current.battler_hp == 0
                and forced_switches < AGATHA_FORCED_SWITCH_LIMIT
                and any(hp > 0 for hp in _party_hp(emulator))
            ):
                terminal = _settle_agatha_forced_switch(
                    reader,
                    actions,
                    emulator,
                )
                forced_switches += 1
                if terminal:
                    note_observed_trainer_battle_exit(battle_intent)
                    break
                continue
            if control_request_matches(error.__cause__, _BoostBoundary.default_action):
                _battle_x_special(reader, actions, emulator)
                boosts_used += 1
                continue
            if not recovery_request_matches(error.__cause__, _HealBoundary):
                cause = error.__cause__
                active = (
                    current.active_party_index,
                    current.battler_hp,
                    current.battler_status,
                )
                raise AgathaChapterError(
                    "Agatha battle runtime failed: "
                    f"runtime={error}, cause={cause!r}, "
                    f"party_hp={_party_hp(emulator)!r}, "
                    f"active={active!r}, "
                    f"enemy={(current.enemy_species_id, current.enemy_hp, current.enemy_level)!r}, "
                    f"pp={current.battler_pp!r}, bag={_bag(emulator)!r}."
                ) from error
            raw = reader.read()
            if (
                (raw.battler_status or 0)
                and (raw.battler_hp or 0) >= AGATHA_RESERVE_SAFE_HP
                and _bag(emulator).get(ItemId.FULL_HEAL, 0)
            ):
                item = ItemId.FULL_HEAL
            elif raw.battler_status or 0:
                item = ItemId.FULL_RESTORE
            else:
                item = (
                    ItemId.HYPER_POTION
                    if _bag(emulator).get(ItemId.HYPER_POTION, 0)
                    else ItemId.FULL_RESTORE
                )
            if _bag(emulator).get(item, 0) == 0:
                raise AgathaChapterError("Agatha exhausted the recovery reserve.") from error
            try:
                terminal_exit = _battle_healing_item(
                    reader,
                    actions,
                    emulator,
                    DEFAULT_SILPH_TIMING,
                    item,
                    party_index=raw.active_party_index or 0,
                )
            except SilphChapterError as healing_error:
                current = reader.read()
                raise AgathaChapterError(
                    "Agatha recovery failed: "
                    f"party_hp={_party_hp(emulator)!r}, "
                    f"enemy={(current.enemy_species_id, current.enemy_hp, current.enemy_level)!r}, "
                    f"active_status={current.battler_status!r}, "
                    f"pp={current.battler_pp!r}, bag={_bag(emulator)!r}."
                ) from healing_error
            if terminal_exit:
                note_observed_trainer_battle_exit(battle_intent)

    for _ in range(20):
        _pulse(actions, MacroActionKind.CANCEL)
    _settle_confirm(actions, reader, 40)
    try:
        for party_index, item in plan_party_recovery(
            _party_hp(emulator),
            _party_max_hp(emulator),
            _party_status(emulator),
        ):
            use_field_recovery_item(actions, reader, emulator, party_index, item)
    except Exception as error:
        raise AgathaChapterError(
            "Post-Agatha recovery failed: "
            f"hp={_party_hp(emulator)!r}, status={_party_status(emulator)!r}, "
            f"bag={_bag(emulator)!r}, cause={error}."
        ) from error
    defeated = reader.read()
    if not _event(defeated, EventFlag.BEAT_AGATHA):
        raise AgathaChapterError("Agatha event did not set after battle.")
    _checkpoint(records, progress, emulator, defeated, "agatha_defeated", "Defeated Agatha")
    _teach_take_down(actions, reader, emulator)
    _move(actions, reader, ("left", "up", "up", "up", "up"), "Lance room entry")
    final = reader.read()

    report = AgathaChapterReport(
        records=tuple(records),
        final_raw=final,
        turns=tuple(turns),
        party=_encounter_party(turns),
        hyper_potions_used=hyper_before - _bag(emulator).get(ItemId.HYPER_POTION, 0),
        full_restores_used=restore_before - _bag(emulator).get(ItemId.FULL_RESTORE, 0),
        x_specials_used=x_special_before - _bag(emulator).get(ItemId.X_SPECIAL, 0),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
        team_switches=team_switches,
    )
    if not report.passed:
        raise AgathaChapterError(f"Agatha terminal evidence failed: {report!r}.")
    return report


def _checkpoint(
    records: list[AgathaCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(AgathaCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            AgathaProgress(
                checkpoint_id,
                label,
                len(records),
                AGATHA_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _encounter_party(turns: Iterable[AgathaTurn]) -> tuple[tuple[int, int], ...]:
    positions: dict[int, tuple[int, int]] = {}
    for turn in turns:
        positions.setdefault(turn.party_position, (turn.species, turn.level))
    return tuple(positions[position] for position in sorted(positions))


def _observed_party_valid(turns: Iterable[AgathaTurn]) -> bool:
    """Validate every policy-visible opponent against Agatha's source roster.

    The opening and final opponents must be visible.  Middle positions may be
    absent when Agatha switches one into an already-selected attack and it
    faints before the next policy decision.
    """

    items = tuple(turns)
    if not items:
        return False
    positions = {item.party_position for item in items}
    return (
        0 in positions
        and len(AGATHA_PARTY) - 1 in positions
        and all(
            0 <= item.party_position < len(AGATHA_PARTY)
            and (item.species, item.level) == AGATHA_PARTY[item.party_position]
            for item in items
        )
    )


def _turns_valid(turns: Iterable[AgathaTurn]) -> bool:
    items = tuple(turns)
    return bool(items) and all(
        item.move_slot in {1, 2, 3, 4} and item.lead_hp > 0 for item in items
    )


def _agatha_matchup_species(raw: RawGameState) -> int:
    """Assign the airborne target to Jolteon and grounded Poison targets to Dugtrio."""
    return JOLTEON_SPECIES_ID if raw.enemy_species_id == 0x82 else DUGTRIO_SPECIES_ID


def _agatha_matchup_switch_target(raw: RawGameState, species_id: int) -> int | None:
    """Resolve one living Agatha specialist by observed species rather than slot."""
    party_hp = raw.party_hp or ()
    for index, species in enumerate(raw.party_species_ids or ()):
        if (
            species == species_id
            and index < len(party_hp)
            and party_hp[index] > 0
            and index != raw.active_party_index
        ):
            return index
    return None


def _agatha_team_lesson_satisfied(turns: Iterable[AgathaTurn]) -> bool:
    """Require both specialists to complete every declared opponent role."""
    items = tuple(turns)
    dugtrio_positions = {
        turn.party_position
        for turn in items
        if turn.active_party_species_id == DUGTRIO_SPECIES_ID
    }
    jolteon_positions = {
        turn.party_position
        for turn in items
        if turn.active_party_species_id == JOLTEON_SPECIES_ID
    }
    return (
        dugtrio_positions >= AGATHA_DUGTRIO_TARGET_POSITIONS
        and jolteon_positions >= AGATHA_JOLTEON_TARGET_POSITIONS
    )


def _agatha_recovery_due(raw: RawGameState) -> bool:
    """Protect the active specialist from Agatha's damage and status sequences."""

    return (raw.battler_hp or 0) < AGATHA_RESERVE_SAFE_HP or bool(raw.battler_status or 0)


def _agatha_move_slot(raw: RawGameState) -> int:
    species = raw.enemy_species_id or 0
    pp = raw.battler_pp or ()
    moves = raw.battler_moves or ()
    if raw.active_party_species_id == DUGTRIO_SPECIES_ID:
        for index, (move, current_pp) in enumerate(zip(moves, pp, strict=True)):
            if move == EARTHQUAKE_MOVE_ID and current_pp & 0x3F:
                return index + 1
        raise AgathaChapterError("Agatha's Dugtrio specialist lacks Earthquake.")
    if raw.active_party_species_id == JOLTEON_SPECIES_ID:
        for move_id in (THUNDER_MOVE_ID, THUNDER_SHOCK_MOVE_ID):
            for index, (move, current_pp) in enumerate(zip(moves, pp, strict=True)):
                if move == move_id and current_pp & 0x3F:
                    return index + 1
        raise AgathaChapterError("Agatha's Jolteon specialist lacks an Electric attack.")
    if raw.active_party_index not in {None, 0}:
        enemy_species = raw.enemy_species_id or 0
        enemy_types = RED_BATTLE_CATALOG.resolve_species(
            pokemon_red_species_ref(enemy_species)
        ).types
        ranked: list[tuple[float, int]] = []
        fallback: list[int] = []
        for slot, (move, remaining) in enumerate(zip(moves, pp, strict=True), start=1):
            if (
                move
                and remaining & 0x3F
                and not (
                    raw.player_disabled_move_slot == slot
                    and (raw.player_disable_turns or 0) > 0
                )
            ):
                fallback.append(slot)
                mechanics = RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move))
                effectiveness = RED_BATTLE_CATALOG.type_effectiveness(
                    mechanics.type_name,
                    enemy_types,
                )
                if mechanics.power > 0 and effectiveness > 0:
                    ranked.append(
                        (mechanics.power * mechanics.accuracy * effectiveness, slot)
                    )
        if ranked:
            return max(ranked)[1]
        if fallback:
            return fallback[0]
        raise AgathaChapterError("Agatha reserve has no legal move with PP.")
    surf_pp = (pp[3] & 0x3F) if len(pp) >= 4 else 0
    surf_disabled = raw.player_disabled_move_slot == 4 and (raw.player_disable_turns or 0) > 0
    if species in {0x82, 0x2D}:
        priorities = (1, 4, 3, 2)
    elif surf_pp > AGATHA_SURF_RESERVE and not surf_disabled:
        priorities = (4, 3, 1, 2)
    else:
        priorities = (3, 4, 1, 2)
    for slot in priorities:
        if (
            len(pp) >= slot
            and pp[slot - 1] & 0x3F
            and not (raw.player_disabled_move_slot == slot and (raw.player_disable_turns or 0) > 0)
        ):
            return slot
    raise AgathaChapterError("Agatha policy has no legal move with PP.")


def _agatha_forced_switch_target(
    party_hp: tuple[int, ...],
    party_species: tuple[int, ...],
    active_party_index: int | None,
    enemy_species: int | None,
) -> int | None:
    """Choose a living teammate with useful coverage for Agatha's opponent."""

    candidates = [
        index for index, hp in enumerate(party_hp) if hp > 0 and index != active_party_index
    ]
    if not candidates:
        return None
    if enemy_species == 0x82:  # Golbat: Electric first, then Flying utility.
        priorities = (JOLTEON_SPECIES_ID, DUX_SPECIES_ID, DUGTRIO_SPECIES_ID)
    else:  # Ghost/Poison and Arbok: Dugtrio's Ground coverage first.
        priorities = (DUGTRIO_SPECIES_ID, JOLTEON_SPECIES_ID, DUX_SPECIES_ID)
    for species in priorities:
        for index in candidates:
            if index < len(party_species) and party_species[index] == species:
                return index
    return max(candidates, key=lambda index: party_hp[index])


def _settle_agatha_forced_switch(
    reader: PokemonRedStateReader,
    actions: CountingExecutor,
    emulator: EmulatorState,
) -> bool:
    """Continue Agatha with a living party member and prove the MAIN menu."""

    initial = reader.read()
    target = _agatha_forced_switch_target(
        _party_hp(emulator),
        initial.party_species_ids or (),
        initial.active_party_index,
        initial.enemy_species_id,
    )
    if target is None:
        raise AgathaChapterError("Agatha KO left no living teammate.")
    for pulse_index in range(64):
        raw = reader.read()
        if raw.battle_state == 0:
            return True
        if (
            raw.battle_state == 2
            and raw.active_party_index == target
            and (raw.battler_hp or 0) > 0
            and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
        ):
            return False
        if raw.battle_state != 2:
            raise AgathaChapterError("Agatha forced switch left the battle.")
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        _pulse(
            actions,
            MacroActionKind.CONFIRM if cursor == target else MacroActionKind.MOVE,
            None if cursor == target else ("down" if cursor < target else "up"),
            DEFAULT_SILPH_TIMING.menu_frames,
        )
        if pulse_index % 5 == 4:
            _pulse(
                actions,
                MacroActionKind.CONFIRM,
                frames=DEFAULT_SILPH_TIMING.menu_frames,
            )
    raise AgathaChapterError("Agatha forced switch exceeded its bounded menu pulses.")


def _battle_x_special(
    reader: PokemonRedStateReader,
    actions: CountingExecutor,
    emulator: EmulatorState,
    *,
    item: ItemId = ItemId.X_SPECIAL,
) -> None:
    raw = reader.read()
    if (
        raw.battle_state != 2
        or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
    ):
        raise AgathaChapterError(f"{item.name} requires the trainer MAIN menu.")
    initial = _bag(emulator).get(item, 0)
    if initial == 0:
        raise AgathaChapterError(f"{item.name} reserve was exhausted.")
    for attempt in range(2):
        before = _bag(emulator).get(item, 0)
        _select_battle_main_command(actions, reader, 1)
        _pulse(actions, MacroActionKind.CONFIRM)
        _select_bag_item(actions, emulator, item, DEFAULT_LAVENDER_TIMING)
        _pulse(actions, MacroActionKind.CONFIRM)
        consumed = False
        for _ in range(30):
            current = reader.read()
            after = _bag(emulator).get(item, 0)
            if after == before - 1:
                consumed = True
            elif after != before:
                raise AgathaChapterError(
                    f"{item.name} changed by an invalid quantity: before={before}, after={after}."
                )
            at_main = (
                current.battle_state == 2
                and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
            )
            if consumed and at_main:
                if initial - after != 1:
                    raise AgathaChapterError(
                        f"{item.name} cumulative use was invalid: initial={initial}, after={after}."
                    )
                return
            if at_main and not consumed:
                break
            # B advances battle text but is inert on the restored MAIN menu.
            # A can spill across the final text boundary and immediately reopen
            # ITEM, consuming a second boost before the next observation.
            _pulse(actions, MacroActionKind.CANCEL)
        else:
            raise AgathaChapterError(
                f"{item.name} use did not settle: before={before}, "
                f"after={_bag(emulator).get(item, 0)}."
            )
        if attempt == 0:
            continue
    raise AgathaChapterError(
        f"{item.name} was not consumed after two bounded selections: "
        f"initial={initial}, after={_bag(emulator).get(item, 0)}."
    )


def _use_field_elixir(actions, reader, emulator) -> None:
    before = _bag(emulator).get(ItemId.ELIXIR, 0)
    if before != AGATHA_ELIXIR_USE:
        raise AgathaChapterError(f"Agatha Elixir reserve mismatch: {before!r}.")
    _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
    _select_bag_item(actions, emulator, ItemId.ELIXIR, DEFAULT_LAVENDER_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    _select_cursor(actions, emulator, 0, DEFAULT_LAVENDER_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        if _bag(emulator).get(ItemId.ELIXIR, 0) == 0:
            _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
            pp = tuple(value & 0x3F for value in (reader.read().first_party_pp or ()))
            if (
                len(pp) != 4
                or not all(value > 0 for value in pp)
                or pp[2] != 10
                or pp[3] <= AGATHA_SURF_RESERVE
            ):
                raise AgathaChapterError(f"Agatha Elixir reload failed: pp={pp!r}.")
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise AgathaChapterError("Agatha Elixir did not restore the lead move PP.")


def _teach_take_down(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    expected_remaining: int = 0,
    expected_moves: tuple[int, int, int, int] = (0x24, 0x46, 0x3A, 0x39),
    replacement_slot: int = 0,
    item: ItemId = ItemId.TM09_TAKE_DOWN,
) -> None:
    _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
    _select_bag_item(
        actions,
        emulator,
        item,
        DEFAULT_LAVENDER_TIMING,
    )
    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (0, 1):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise AgathaChapterError(f"{item.name} did not reach party selection.")
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (5, 8) and _menu_cursor_active(emulator):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise AgathaChapterError(f"{item.name} did not reach move deletion.")
    for _ in range(replacement_slot):
        _pulse(actions, MacroActionKind.MOVE, "down")
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        raw = reader.read()
        if (
            raw.first_party_moves == expected_moves
            and _bag(emulator).get(item, 0) == expected_remaining
        ):
            _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise AgathaChapterError(
        f"{item.name} did not install the expected move set: "
        f"actual={reader.read().first_party_moves!r}, expected={expected_moves!r}, "
        f"remaining={_bag(emulator).get(item, 0)}, expected_remaining={expected_remaining}."
    )
