"""Qualified Lance chapter for the pinned Pokémon Red runtime."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.agatha import (
    AgathaChapterError,
    _battle_x_special,
    _teach_take_down,
)
from pokemon_red_completion.battle_actions import (
    BattleAction,
    BattleBoostStat,
    BattleControlRequest,
    control_request_matches,
    recovery_request_matches,
)
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRecoveryCapability,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    note_observed_trainer_battle_exit,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.bruno import BrunoChapterError, _teach_mega_punch
from pokemon_red_completion.celadon import (
    _bag,
    _party_hp,
    _party_max_hp,
    _party_status,
)
from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _close_menus,
    _open_bag,
    _select_bag_item,
    _select_cursor,
)
from pokemon_red_completion.lorelei import LoreleiChapterError, _battle_x_accuracy
from pokemon_red_completion.observation import (
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.silph import (
    DEFAULT_SILPH_TIMING,
    SilphChapterError,
    _battle_healing_item,
)
from pokemon_red_completion.tower import party_core_intact
from pokemon_red_completion.victory_road import (
    VictoryRoadChapterError,
    _battle_sacrifice,
    _event,
    _move,
    _pulse,
    _settle_confirm,
)

LANCE_CHECKPOINT_COUNT = 3
LANCE_PARTY = (
    (0x16, 58),
    (0x59, 56),
    (0x59, 56),
    (0xAB, 60),
    (0x42, 62),
)
LANCE_APPROACH = ("up",) * 9
LANCE_SAFE_HP = 120
LANCE_CHAMPION_SURF_RESERVE = 0
LANCE_CHAMPION_FULL_RESTORE_RESERVE = 2
LANCE_RNG_DELAY_FRAMES = 40
LANCE_X_SPECIAL_USE = 1
LANCE_AERODACTYL_PIVOT_SPECIES = 0xAB
LANCE_HELPER_PIVOT_LIMIT = 2


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class LanceChapterError(RuntimeError):
    """Raised when the Lance evidence contract fails."""


@dataclass(frozen=True, slots=True)
class LanceProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[LanceProgress], None]


@dataclass(frozen=True, slots=True)
class LanceCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class LanceTurn:
    species: int
    level: int
    enemy_hp: int
    lead_hp: int
    lead_status: int
    pp: tuple[int, int, int, int]
    move_slot: int
    party_position: int = 0


@dataclass(frozen=True, slots=True)
class LanceChapterReport:
    records: tuple[LanceCheckpoint, ...]
    final_raw: RawGameState
    turns: tuple[LanceTurn, ...]
    party: tuple[tuple[int, int], ...]
    hyper_potions_used: int
    full_restores_used: int
    full_heals_used: int
    x_accuracy_used: int
    x_attacks_used: int
    x_specials_used: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == LANCE_CHECKPOINT_COUNT
            and self.party == LANCE_PARTY
            and _turns_valid(self.turns)
            and self.x_accuracy_used == 1
            and self.x_attacks_used == 1
            and self.x_specials_used == LANCE_X_SPECIAL_USE
            and _event(self.final_raw, EventFlag.BEAT_LANCE)
            and self.final_raw.map_id == MapId.CHAMPIONS_ROOM
            and party_core_intact(self.final_raw.party_species_ids)
            and self.final_raw.first_party_moves == (0x05, 0x46, 0x3B, 0x39)
            and all(hp > 0 for hp in self.party_hp)
            and all(status == 0 for status in self.party_status)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "defeat_lance",
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
                }
                for item in self.turns
            ],
            "recovery": {
                "hyper_potions_used": self.hyper_potions_used,
                "full_restores_used": self.full_restores_used,
                "full_heals_used": self.full_heals_used,
                "x_accuracy_used": self.x_accuracy_used,
                "x_attacks_used": self.x_attacks_used,
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


def run_lance_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> LanceChapterReport:
    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[LanceCheckpoint] = []
    initial = reader.read()
    if (
        initial.map_id != MapId.LANCES_ROOM
        or not party_core_intact(initial.party_species_ids)
        or not _event(initial, EventFlag.BEAT_AGATHA)
        or _event(initial, EventFlag.BEAT_LANCE)
        or _bag(emulator).get(ItemId.ELIXIR, 0) != 0
        or _bag(emulator).get(ItemId.X_ACCURACY, 0) != 2
        or _bag(emulator).get(ItemId.X_ATTACK, 0) != 1
    ):
        raise LanceChapterError("Lance input boundary is not qualified.")
    _settle_confirm(actions, reader, 200)
    ready = reader.read()
    if (ready.player_x, ready.player_y) != (6, 11):
        raise LanceChapterError("Lance entrance autowalk did not settle.")
    _checkpoint(records, progress, emulator, ready, "lance_ready", "Lance room ready")

    try:
        _teach_mega_punch(
            actions,
            reader,
            emulator,
            expected_remaining=0,
        )
    except BrunoChapterError as error:
        raise LanceChapterError(f"Lance Mega Punch reload failed: {error}") from error
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=LANCE_RNG_DELAY_FRAMES))
    _move(actions, reader, LANCE_APPROACH[:-1], "Lance approach")
    _pulse(actions, MacroActionKind.MOVE, "up", 240)
    for _ in range(40):
        if reader.read().battle_state == 2:
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise LanceChapterError("Lance battle did not start.")
    _checkpoint(records, progress, emulator, reader.read(), "lance_engaged", "Engaged Lance")

    turns: list[LanceTurn] = []

    class _HealBoundary(BattleControlRequest):
        default_action = BattleAction.recovery()

    class _BoostBoundary(BattleControlRequest):
        default_action = BattleAction.boost(BattleBoostStat.SPECIAL)

    class _AccuracyBoundary(BattleControlRequest):
        default_action = BattleAction.boost(BattleBoostStat.ACCURACY)

    class _AttackBoundary(BattleControlRequest):
        default_action = BattleAction.boost(BattleBoostStat.ATTACK)

    last_recovery_turn = -1
    boosts_used = 0
    accuracy_used = 0
    attacks_used = 0
    helper_pivots_used = 0

    def policy(raw: RawGameState) -> int:
        if accuracy_used == 0:
            raise _AccuracyBoundary
        if attacks_used == 0:
            raise _AttackBoundary
        if boosts_used < LANCE_X_SPECIAL_USE:
            raise _BoostBoundary
        hp = raw.first_party_hp or 0
        status = raw.first_party_status or 0
        recovery_threshold = _lance_recovery_threshold(raw)
        hp_recovery = bool(
            _bag(emulator).get(ItemId.HYPER_POTION, 0)
            or _bag(emulator).get(ItemId.FULL_RESTORE, 0)
            > LANCE_CHAMPION_FULL_RESTORE_RESERVE
        )
        status_recovery = bool(
            _bag(emulator).get(ItemId.FULL_HEAL, 0)
            or _bag(emulator).get(ItemId.FULL_RESTORE, 0)
            > LANCE_CHAMPION_FULL_RESTORE_RESERVE
        )
        if (
            ((hp < recovery_threshold and hp_recovery) or (status and status_recovery))
            and len(turns) != last_recovery_turn
        ):
            raise _HealBoundary
        species = raw.enemy_species_id or 0
        pp = raw.first_party_pp or (0, 0, 0, 0)
        slot = _lance_move_slot(raw)
        turns.append(
            LanceTurn(
                species,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                hp,
                status,
                pp,
                slot,
                emulator.read_u8(RamAddress.ENEMY_MON_PARTY_POS),
            )
        )
        return slot

    hyper_before = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    restore_before = _bag(emulator).get(ItemId.FULL_RESTORE, 0)
    heal_before = _bag(emulator).get(ItemId.FULL_HEAL, 0)
    accuracy_before = _bag(emulator).get(ItemId.X_ACCURACY, 0)
    attack_before = _bag(emulator).get(ItemId.X_ATTACK, 0)
    x_special_before = _bag(emulator).get(ItemId.X_SPECIAL, 0)
    battle_intent = BattleIntent(
        "defeat_lance",
        battle_plan_id=RedBattlePlanId.LEAGUE_LANCE,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
        recovery_capabilities=frozenset(
            {
                BattleRecoveryCapability.RESTORE_HP,
                BattleRecoveryCapability.CURE_ANY_STATUS,
            }
        ),
    )
    while reader.read().battle_state:
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                policy,
                expected_map=MapId.LANCES_ROOM,
                intent=battle_intent,
                timing=BattleRuntimeTiming(
                    max_runtime_pulses=1800,
                    max_post_attack_transition_pulses=30,
                ),
                label="Lance",
            )
        except BattleRuntimeError as error:
            if control_request_matches(error.__cause__, _AccuracyBoundary.default_action):
                try:
                    _battle_x_accuracy(reader, actions, emulator)
                except LoreleiChapterError as accuracy_error:
                    raise LanceChapterError("Lance X Accuracy setup failed.") from accuracy_error
                accuracy_used += 1
                continue
            if control_request_matches(error.__cause__, _AttackBoundary.default_action):
                try:
                    _battle_x_special(reader, actions, emulator, item=ItemId.X_ATTACK)
                except AgathaChapterError as attack_error:
                    raise LanceChapterError("Lance X Attack setup failed.") from attack_error
                attacks_used += 1
                continue
            if control_request_matches(error.__cause__, _BoostBoundary.default_action):
                try:
                    _battle_x_special(reader, actions, emulator)
                except AgathaChapterError as boost_error:
                    raise LanceChapterError("Lance X Special setup failed.") from boost_error
                boosts_used += 1
                continue
            if not recovery_request_matches(error.__cause__, _HealBoundary):
                raw = reader.read()
                raise LanceChapterError(
                    "Lance battle runtime failed: "
                    f"party_hp={_party_hp(emulator)!r}, "
                    f"party_max_hp={_party_max_hp(emulator)!r}, "
                    f"enemy={(raw.enemy_species_id, raw.enemy_hp, raw.enemy_level)!r}, "
                    f"lead_status={raw.first_party_status!r}, "
                    f"pp={raw.first_party_pp!r}, bag={_bag(emulator)!r}, "
                    f"turns={turns!r}."
                ) from error
            raw = reader.read()
            if (
                (raw.first_party_status or 0)
                and (raw.first_party_hp or 0) >= 90
                and _bag(emulator).get(ItemId.FULL_HEAL, 0)
            ):
                item = ItemId.FULL_HEAL
            elif (raw.first_party_status or 0) and _bag(emulator).get(
                ItemId.FULL_RESTORE, 0
            ) > LANCE_CHAMPION_FULL_RESTORE_RESERVE:
                item = ItemId.FULL_RESTORE
            elif _bag(emulator).get(ItemId.HYPER_POTION, 0):
                item = ItemId.HYPER_POTION
            elif (
                _bag(emulator).get(ItemId.FULL_RESTORE, 0)
                > LANCE_CHAMPION_FULL_RESTORE_RESERVE
            ):
                item = ItemId.FULL_RESTORE
            else:
                item = ItemId.FULL_HEAL
            if _bag(emulator).get(item, 0) == 0:
                raise LanceChapterError(
                    "Lance exhausted the selected recovery reserve: "
                    f"item={item.name}, bag={_bag(emulator)!r}, "
                    f"party_hp={_party_hp(emulator)!r}."
                ) from error
            helper_index = _next_lance_helper(
                _party_hp(emulator), _party_max_hp(emulator)
            )
            if _should_use_lance_helper_pivot(
                raw,
                helper_index=helper_index,
                helper_pivots_used=helper_pivots_used,
            ):
                try:
                    _battle_sacrifice(
                        actions,
                        reader,
                        emulator,
                        helper_index,
                        heal_lead=True,
                        healing_item=item,
                    )
                except VictoryRoadChapterError as pivot_error:
                    raise LanceChapterError("Lance recovery pivot failed.") from pivot_error
                helper_pivots_used += 1
            else:
                try:
                    terminal_exit = _battle_healing_item(
                        reader,
                        actions,
                        emulator,
                        DEFAULT_SILPH_TIMING,
                        item,
                    )
                except SilphChapterError as healing_error:
                    raise LanceChapterError("Lance recovery failed.") from healing_error
                if terminal_exit:
                    note_observed_trainer_battle_exit(battle_intent)
            last_recovery_turn = len(turns)

    for _ in range(20):
        _pulse(actions, MacroActionKind.CANCEL)
    _settle_confirm(actions, reader, 40)
    _recover_fainted_helpers(actions, reader, emulator)
    _field_recover(actions, reader, emulator)
    _field_recover_helpers(actions, reader, emulator)
    defeated = reader.read()
    if not _event(defeated, EventFlag.BEAT_LANCE):
        raise LanceChapterError("Lance event did not set after battle.")
    _checkpoint(records, progress, emulator, defeated, "lance_defeated", "Defeated Lance")
    try:
        _teach_take_down(
            actions,
            reader,
            emulator,
            expected_remaining=0,
            expected_moves=(0x05, 0x46, 0x3B, 0x39),
            replacement_slot=2,
            item=ItemId.TM14_BLIZZARD,
        )
    except AgathaChapterError as error:
        raise LanceChapterError(f"Champion coverage installation failed: {error}") from error
    _move(actions, reader, ("left", "up", "up", "up"), "Champion room entry")
    final = reader.read()

    report = LanceChapterReport(
        records=tuple(records),
        final_raw=final,
        turns=tuple(turns),
        party=_encounter_party(turns),
        hyper_potions_used=hyper_before - _bag(emulator).get(ItemId.HYPER_POTION, 0),
        full_restores_used=restore_before - _bag(emulator).get(ItemId.FULL_RESTORE, 0),
        full_heals_used=heal_before - _bag(emulator).get(ItemId.FULL_HEAL, 0),
        x_accuracy_used=accuracy_before - _bag(emulator).get(ItemId.X_ACCURACY, 0),
        x_attacks_used=attack_before - _bag(emulator).get(ItemId.X_ATTACK, 0),
        x_specials_used=x_special_before - _bag(emulator).get(ItemId.X_SPECIAL, 0),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise LanceChapterError(f"Lance terminal evidence failed: {report!r}.")
    return report


def _field_recover(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    hp = _party_hp(emulator)[0]
    max_hp = _party_max_hp(emulator)[0]
    status = _party_status(emulator)[0]
    item = _lance_field_recovery_item(
        hp=hp,
        max_hp=max_hp,
        status=status,
        inventory=_bag(emulator),
    )
    if item is None:
        if status:
            raise LanceChapterError("Lance left an uncured status with no recovery item.")
        if hp <= 0:
            raise LanceChapterError("Lance left the party lead fainted.")
        return
    _use_field_item_on_party(
        actions,
        reader,
        emulator,
        item,
        0,
    )
    if _party_status(emulator)[0]:
        _field_recover(actions, reader, emulator)


def _lance_field_recovery_item(
    *,
    hp: int,
    max_hp: int,
    status: int,
    inventory: Mapping[ItemId, int],
) -> ItemId | None:
    """Use field supplies without spending the Champion's Full Restore reserve."""
    if status and inventory.get(ItemId.FULL_HEAL, 0):
        return ItemId.FULL_HEAL
    if hp < max_hp and inventory.get(ItemId.HYPER_POTION, 0):
        return ItemId.HYPER_POTION
    if status:
        raise LanceChapterError("Lance left an uncured status with no recovery item.")
    return None


def _recover_fainted_helpers(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    for party_index in (1, 2):
        if _party_hp(emulator)[party_index] == 0:
            _use_field_item_on_party(
                actions,
                reader,
                emulator,
                ItemId.REVIVE,
                party_index,
            )
    if not all(hp > 0 for hp in _party_hp(emulator)[1:]):
        raise LanceChapterError("Lance helper recovery did not revive the full party.")


def _field_recover_helpers(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    for party_index in (1, 2):
        hp = _party_hp(emulator)[party_index]
        max_hp = _party_max_hp(emulator)[party_index]
        if hp == max_hp:
            continue
        if not _bag(emulator).get(ItemId.HYPER_POTION, 0):
            continue
        item = ItemId.HYPER_POTION
        _use_field_item_on_party(
            actions,
            reader,
            emulator,
            item,
            party_index,
        )
    if not all(hp > 0 for hp in _party_hp(emulator)[1:]):
        raise LanceChapterError("Lance helper recovery left a helper fainted.")


def _use_field_item_on_party(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    item: ItemId,
    party_index: int,
) -> None:
    before = _bag(emulator).get(item, 0)
    if before <= 0:
        raise LanceChapterError(f"Lance helper recovery exhausted {item.name}.")
    _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
    _select_bag_item(actions, emulator, item, DEFAULT_LAVENDER_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    _select_cursor(actions, emulator, party_index, DEFAULT_LAVENDER_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        if _bag(emulator).get(item, 0) == before - 1:
            _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise LanceChapterError(f"Lance helper recovery did not consume {item.name}.")


def _checkpoint(
    records: list[LanceCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(LanceCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            LanceProgress(
                checkpoint_id,
                label,
                len(records),
                LANCE_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _encounter_party(turns: Iterable[LanceTurn]) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    previous: LanceTurn | None = None
    for turn in turns:
        identity = (turn.species, turn.level)
        if (
            not result
            or result[-1] != identity
            or (
                previous is not None
                and (previous.species, previous.level) == identity
                and turn.party_position != previous.party_position
            )
        ):
            result.append(identity)
        previous = turn
    return tuple(result)


def _next_lance_helper(
    party_hp: tuple[int, ...],
    party_max_hp: tuple[int, ...] | None = None,
) -> int | None:
    """Return a living weak helper, never a trained teammate, for recovery."""

    return next(
        (
            index
            for index, hp in enumerate(party_hp[1:], start=1)
            if hp > 0
            and (party_max_hp is None or party_max_hp[index] <= 100)
        ),
        None,
    )


def _should_use_lance_helper_pivot(
    raw: RawGameState,
    *,
    helper_index: int | None,
    helper_pivots_used: int,
) -> bool:
    """Never sacrifice more helpers than the fixed two-Revive handoff can restore."""

    return (
        helper_index is not None
        and helper_pivots_used < LANCE_HELPER_PIVOT_LIMIT
        and (raw.first_party_hp or 0) < _lance_recovery_threshold(raw)
    )


def _lance_recovery_threshold(raw: RawGameState) -> int:
    """Protect the inaccurate last-resort finisher with a full-health boundary."""

    if raw.enemy_species_id == 0x16:
        # Lance's opening Gyarados can follow ordinary chip with a lethal
        # high-roll Hydro Pump.  Heal before giving it that knockout window.
        return max(LANCE_SAFE_HP, raw.first_party_max_hp or 0)
    pp = tuple(value & 0x3F for value in (raw.first_party_pp or ()))
    if len(pp) == 4 and pp[0] > 0 and not any(pp[1:]):
        return max(LANCE_SAFE_HP, raw.first_party_max_hp or 0)
    return LANCE_SAFE_HP


def _lance_move_slot(raw: RawGameState) -> int:
    species = raw.enemy_species_id or 0
    pp = raw.first_party_pp or ()
    if species == 0x16:
        priorities = (1, 3, 2, 4)
    elif species == 0xAB:
        priorities = (4, 3, 2, 1)
    elif species == 0x59:
        priorities = (3, 2, 1, 4)
    elif species == 0x42:
        surf_pp = (pp[3] & 0x3F) if len(pp) >= 4 else 0
        priorities = (
            (3, 4, 2, 1)
            if surf_pp > LANCE_CHAMPION_SURF_RESERVE
            else (3, 2, 1, 4)
        )
    else:
        priorities = (3, 2, 1, 4)
    for slot in priorities:
        if (
            len(pp) >= slot
            and pp[slot - 1] & 0x3F
            and not (
                raw.player_disabled_move_slot == slot
                and (raw.player_disable_turns or 0) > 0
            )
        ):
            return slot
    raise LanceChapterError("Lance policy has no legal move with PP.")


def _turns_valid(turns: Iterable[LanceTurn]) -> bool:
    items = tuple(turns)
    return bool(items) and all(
        item.species in {species for species, _ in LANCE_PARTY}
        and item.move_slot in {1, 2, 3, 4}
        and item.lead_hp > 0
        and item.lead_status == 0
        for item in items
    )
