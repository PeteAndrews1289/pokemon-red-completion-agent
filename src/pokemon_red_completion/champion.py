"""Qualified Champion and Hall of Fame chapter for Pokémon Red."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.celadon import _bag, _party_hp, _party_status
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
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
from pokemon_red_completion.silph import (
    DEFAULT_SILPH_TIMING,
    SilphChapterError,
    _battle_healing_item,
)
from pokemon_red_completion.tower import TOWER_FINAL_PARTY
from pokemon_red_completion.victory_road import (
    _CountingExecutor,
    _event,
    _pulse,
    _select_battle_main_command,
)

CHAMPION_CHECKPOINT_COUNT = 3
CHAMPION_RNG_DELAY_FRAMES = 25
CHAMPION_SAFE_HP = 40
CHAMPION_PARTY = (
    (0x97, 61),
    (0x95, 59),
    (0x01, 61),
    (0x16, 61),
    (0x14, 63),
    (0x9A, 65),
)


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class ChampionChapterError(RuntimeError):
    """Raised when the Champion completion contract fails."""


@dataclass(frozen=True, slots=True)
class ChampionProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[ChampionProgress], None]


@dataclass(frozen=True, slots=True)
class ChampionCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class ChampionTurn:
    species: int
    level: int
    enemy_hp: int
    lead_hp: int
    lead_status: int
    pp: tuple[int, int, int, int]
    move_slot: int
    party_position: int


@dataclass(frozen=True, slots=True)
class ChampionChapterReport:
    records: tuple[ChampionCheckpoint, ...]
    final_raw: RawGameState
    turns: tuple[ChampionTurn, ...]
    party: tuple[tuple[int, int], ...]
    hyper_potions_used: int
    full_restores_used: int
    full_heals_used: int
    x_specials_used: int
    party_hp: tuple[int, int, int]
    party_status: tuple[int, int, int]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == CHAMPION_CHECKPOINT_COUNT
            and self.party == CHAMPION_PARTY
            and _turns_valid(self.turns)
            and self.x_specials_used == 6
            and _event(self.final_raw, EventFlag.BEAT_CHAMPION_RIVAL)
            and self.final_raw.map_id == MapId.HALL_OF_FAME
            and self.final_raw.party_species_ids == TOWER_FINAL_PARTY
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "enter_hall_of_fame",
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
            "resources": {
                "hyper_potions_used": self.hyper_potions_used,
                "full_restores_used": self.full_restores_used,
                "full_heals_used": self.full_heals_used,
                "x_specials_used": self.x_specials_used,
            },
            "terminal": {
                "map": int(self.final_raw.map_id),
                "position": [self.final_raw.player_x, self.final_raw.player_y],
                "party_hp": list(self.party_hp),
                "party_status": list(self.party_status),
                "moves": list(self.final_raw.first_party_moves or ()),
                "pp": list(self.final_raw.first_party_pp or ()),
                "champion_event": _event(
                    self.final_raw,
                    EventFlag.BEAT_CHAMPION_RIVAL,
                ),
                "hall_of_fame": self.final_raw.map_id == MapId.HALL_OF_FAME,
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


def run_champion_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> ChampionChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[ChampionCheckpoint] = []
    initial = reader.read()
    if (
        initial.map_id != MapId.CHAMPIONS_ROOM
        or (initial.player_x, initial.player_y) != (4, 3)
        or initial.party_species_ids != TOWER_FINAL_PARTY
        or not _event(initial, EventFlag.BEAT_LANCE)
        or _event(initial, EventFlag.BEAT_CHAMPION_RIVAL)
        or _bag(emulator).get(ItemId.X_SPECIAL, 0) != 6
    ):
        raise ChampionChapterError("Champion input boundary is not qualified.")
    _checkpoint(
        records,
        progress,
        emulator,
        initial,
        "champion_ready",
        "Champion room ready",
    )
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=CHAMPION_RNG_DELAY_FRAMES))
    for _ in range(50):
        if reader.read().battle_state == 2:
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise ChampionChapterError("Champion battle did not start.")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "champion_engaged",
        "Engaged Champion",
    )

    turns: list[ChampionTurn] = []
    boosts_used = 0

    class _HealBoundary(Exception):
        pass

    class _BoostBoundary(Exception):
        pass

    def policy(raw: RawGameState) -> int:
        hp = raw.first_party_hp or 0
        status = raw.first_party_status or 0
        if hp < CHAMPION_SAFE_HP or status:
            raise _HealBoundary
        if boosts_used < 6:
            raise _BoostBoundary
        pp = raw.first_party_pp or (0, 0, 0, 0)
        species = raw.enemy_species_id or 0
        if species in {0x01, 0x14} and pp[3] > 0:
            slot = 4
        elif pp[0] > 0:
            slot = 1
        elif pp[1] > 0:
            slot = 2
        else:
            slot = 4
        turns.append(
            ChampionTurn(
                species=species,
                level=raw.enemy_level or 0,
                enemy_hp=raw.enemy_hp or 0,
                lead_hp=hp,
                lead_status=status,
                pp=pp,
                move_slot=slot,
                party_position=emulator.read_u8(RamAddress.ENEMY_MON_PARTY_POS),
            )
        )
        return slot

    hyper_before = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    restore_before = _bag(emulator).get(ItemId.FULL_RESTORE, 0)
    heal_before = _bag(emulator).get(ItemId.FULL_HEAL, 0)
    x_special_before = _bag(emulator).get(ItemId.X_SPECIAL, 0)
    while True:
        raw = reader.read()
        if _completed(raw):
            break
        if raw.battle_state != 2:
            _pulse(actions, MacroActionKind.CONFIRM)
            continue
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                policy,
                expected_map=MapId.CHAMPIONS_ROOM,
                intent=BattleIntent(
                    "defeat_champion",
                    battle_plan_id=RedBattlePlanId.LEAGUE_CHAMPION,
                    resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
                ),
                timing=BattleRuntimeTiming(
                    max_runtime_pulses=3000,
                    max_post_attack_transition_pulses=30,
                ),
                label="Champion",
            )
        except BattleRuntimeError as error:
            if _completed(reader.read()):
                break
            if isinstance(error.__cause__, _BoostBoundary):
                _battle_x_special(reader, actions, emulator)
                boosts_used += 1
                continue
            if not isinstance(error.__cause__, _HealBoundary):
                raise ChampionChapterError("Champion battle runtime failed.") from error
            current = reader.read()
            if (current.first_party_status or 0) and (
                current.first_party_hp or 0
            ) >= CHAMPION_SAFE_HP:
                item = ItemId.FULL_HEAL
            else:
                item = ItemId.FULL_RESTORE
            if _bag(emulator).get(item, 0) == 0:
                raise ChampionChapterError("Champion exhausted the recovery reserve.") from error
            try:
                _battle_healing_item(
                    reader,
                    actions,
                    emulator,
                    DEFAULT_SILPH_TIMING,
                    item,
                )
            except SilphChapterError as healing_error:
                raise ChampionChapterError("Champion recovery failed.") from healing_error

    final = reader.read()
    _checkpoint(
        records,
        progress,
        emulator,
        final,
        "hall_of_fame",
        "Champion defeated and Hall of Fame entered",
    )
    report = ChampionChapterReport(
        records=tuple(records),
        final_raw=final,
        turns=tuple(turns),
        party=_encounter_party(turns),
        hyper_potions_used=hyper_before - _bag(emulator).get(ItemId.HYPER_POTION, 0),
        full_restores_used=restore_before - _bag(emulator).get(ItemId.FULL_RESTORE, 0),
        full_heals_used=heal_before - _bag(emulator).get(ItemId.FULL_HEAL, 0),
        x_specials_used=x_special_before - _bag(emulator).get(ItemId.X_SPECIAL, 0),
        party_hp=_party_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise ChampionChapterError(f"Champion terminal evidence failed: {report!r}.")
    return report


def _battle_x_special(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    emulator: EmulatorState,
) -> None:
    raw = reader.read()
    if (
        raw.battle_state != 2
        or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
    ):
        raise ChampionChapterError("X Special gate requires the trainer MAIN menu.")
    before = _bag(emulator).get(ItemId.X_SPECIAL, 0)
    if before == 0:
        raise ChampionChapterError("X Special reserve was exhausted.")
    _select_battle_main_command(actions, reader, 1)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_bag_item(
        actions,
        emulator,
        ItemId.X_SPECIAL,
        DEFAULT_LAVENDER_TIMING,
    )
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(30):
        current = reader.read()
        if (
            current.battle_state == 2
            and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise ChampionChapterError("X Special did not return to the MAIN battle menu.")
    if before - _bag(emulator).get(ItemId.X_SPECIAL, 0) != 1:
        raise ChampionChapterError("X Special quantity did not decrement exactly once.")


def _completed(raw: RawGameState) -> bool:
    return raw.map_id == MapId.HALL_OF_FAME and _event(raw, EventFlag.BEAT_CHAMPION_RIVAL)


def _encounter_party(
    turns: Iterable[ChampionTurn],
) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    previous_position: int | None = None
    for turn in turns:
        if turn.party_position != previous_position:
            result.append((turn.species, turn.level))
            previous_position = turn.party_position
    return tuple(result)


def _turns_valid(turns: Iterable[ChampionTurn]) -> bool:
    items = tuple(turns)
    return bool(items) and all(
        item.species in {species for species, _ in CHAMPION_PARTY}
        and item.move_slot in {1, 2, 4}
        and item.lead_hp >= CHAMPION_SAFE_HP
        and item.lead_status == 0
        for item in items
    )


def _checkpoint(
    records: list[ChampionCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(ChampionCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            ChampionProgress(
                checkpoint_id,
                label,
                len(records),
                CHAMPION_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )
