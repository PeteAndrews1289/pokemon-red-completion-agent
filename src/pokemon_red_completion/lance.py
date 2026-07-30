"""Qualified Lance chapter for the pinned Pokémon Red runtime."""

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
from pokemon_red_completion.bruno import BrunoChapterError, _teach_mega_punch
from pokemon_red_completion.celadon import (
    _bag,
    _party_hp,
    _party_max_hp,
    _party_status,
)
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _use_bag_item,
)
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
from pokemon_red_completion.tower import TOWER_FINAL_PARTY
from pokemon_red_completion.victory_road import (
    _CountingExecutor,
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
LANCE_SAFE_HP = 110
LANCE_RNG_DELAY_FRAMES = 1


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


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
    party_hp: tuple[int, int, int]
    party_max_hp: tuple[int, int, int]
    party_status: tuple[int, int, int]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == LANCE_CHECKPOINT_COUNT
            and self.party == LANCE_PARTY
            and _turns_valid(self.turns)
            and _event(self.final_raw, EventFlag.BEAT_LANCE)
            and self.final_raw.map_id == MapId.CHAMPIONS_ROOM
            and self.final_raw.party_species_ids == TOWER_FINAL_PARTY
            and self.final_raw.first_party_moves == (0x05, 0x46, 0x3A, 0x39)
            and self.party_hp == self.party_max_hp
            and self.party_status == (0, 0, 0)
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
    actions = _CountingExecutor(executor)
    records: list[LanceCheckpoint] = []
    initial = reader.read()
    if (
        initial.map_id != MapId.LANCES_ROOM
        or initial.party_species_ids != TOWER_FINAL_PARTY
        or not _event(initial, EventFlag.BEAT_AGATHA)
        or _event(initial, EventFlag.BEAT_LANCE)
    ):
        raise LanceChapterError("Lance input boundary is not qualified.")
    _settle_confirm(actions, reader, 200)
    ready = reader.read()
    if (ready.player_x, ready.player_y) != (6, 11):
        raise LanceChapterError("Lance entrance autowalk did not settle.")
    _checkpoint(records, progress, emulator, ready, "lance_ready", "Lance room ready")

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

    class _HealBoundary(Exception):
        pass

    def policy(raw: RawGameState) -> int:
        hp = raw.first_party_hp or 0
        status = raw.first_party_status or 0
        if hp < LANCE_SAFE_HP or status:
            raise _HealBoundary
        species = raw.enemy_species_id or 0
        pp = raw.first_party_pp or (0, 0, 0, 0)
        if species == 0xAB and pp[3] > 0:
            slot = 4
        elif pp[1] > 0:
            slot = 2
        elif pp[0] > 0:
            slot = 1
        else:
            slot = 4
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
    while reader.read().battle_state:
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                policy,
                expected_map=MapId.LANCES_ROOM,
                intent=BattleIntent(
                    "defeat_lance",
                    battle_plan_id=RedBattlePlanId.LEAGUE_LANCE,
                    resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
                ),
                timing=BattleRuntimeTiming(
                    max_runtime_pulses=1800,
                    max_post_attack_transition_pulses=30,
                ),
                label="Lance",
            )
        except BattleRuntimeError as error:
            if not isinstance(error.__cause__, _HealBoundary):
                raise LanceChapterError("Lance battle runtime failed.") from error
            raw = reader.read()
            if (raw.first_party_status or 0) and (raw.first_party_hp or 0) >= 90:
                item = ItemId.FULL_HEAL
            elif raw.first_party_status or 0:
                item = ItemId.FULL_RESTORE
            elif _bag(emulator).get(ItemId.HYPER_POTION, 0):
                item = ItemId.HYPER_POTION
            else:
                item = ItemId.FULL_RESTORE
            if _bag(emulator).get(item, 0) == 0:
                raise LanceChapterError("Lance exhausted the recovery reserve.") from error
            try:
                _battle_healing_item(
                    reader,
                    actions,
                    emulator,
                    DEFAULT_SILPH_TIMING,
                    item,
                )
            except SilphChapterError as healing_error:
                raise LanceChapterError("Lance recovery failed.") from healing_error

    for _ in range(20):
        _pulse(actions, MacroActionKind.CANCEL)
    _settle_confirm(actions, reader, 40)
    _field_recover(actions, reader, emulator)
    defeated = reader.read()
    if not _event(defeated, EventFlag.BEAT_LANCE):
        raise LanceChapterError("Lance event did not set after battle.")
    _checkpoint(records, progress, emulator, defeated, "lance_defeated", "Defeated Lance")
    try:
        _teach_mega_punch(
            actions,
            reader,
            emulator,
            expected_remaining=0,
        )
    except BrunoChapterError as error:
        raise LanceChapterError("Champion Mega Punch reload failed.") from error
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
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    hp = _party_hp(emulator)[0]
    max_hp = _party_max_hp(emulator)[0]
    status = _party_status(emulator)[0]
    if hp == max_hp and not status:
        return
    if status and hp < max_hp and _bag(emulator).get(ItemId.FULL_RESTORE, 0):
        item = ItemId.FULL_RESTORE
    elif hp < max_hp and _bag(emulator).get(ItemId.HYPER_POTION, 0):
        item = ItemId.HYPER_POTION
    elif status:
        item = ItemId.FULL_HEAL
    else:
        item = ItemId.FULL_RESTORE
    _use_bag_item(
        actions,
        reader,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        item,
    )
    if _party_hp(emulator)[0] != max_hp or _party_status(emulator)[0]:
        _field_recover(actions, reader, emulator)


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


def _turns_valid(turns: Iterable[LanceTurn]) -> bool:
    items = tuple(turns)
    return bool(items) and all(
        item.species in {species for species, _ in LANCE_PARTY}
        and item.move_slot in {1, 2, 4}
        and item.lead_hp >= LANCE_SAFE_HP
        and item.lead_status == 0
        for item in items
    )
