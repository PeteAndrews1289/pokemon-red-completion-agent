"""Qualified Bruno chapter.

Room coordinates and trainer data are pinned to pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8`` and verified against the
supported English Pokémon Red ROM.
"""

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
    recovery_action_due,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.blaine import _select_cursor
from pokemon_red_completion.celadon import (
    _bag,
    _party_hp,
    _party_max_hp,
    _party_status,
)
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _close_menus,
    _open_bag,
    _select_bag_item,
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
    _menu_cursor_active,
    _move,
    _pulse,
    _settle_confirm,
)

BRUNO_CHECKPOINT_COUNT = 3
BRUNO_PARTY = (
    (0x22, 53),
    (0x2C, 55),
    (0x2B, 55),
    (0x22, 56),
    (0x7E, 58),
)
BRUNO_APPROACH = ("right", "up", "up")
BRUNO_RNG_DELAY_FRAMES = 185
BRUNO_SAFE_HP = 90
BRUNO_HITMONLEE_SAFE_HP = 120
BRUNO_LANCE_SURF_RESERVE = 1


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class BrunoChapterError(RuntimeError):
    """Raised when the Bruno evidence contract fails."""


@dataclass(frozen=True, slots=True)
class BrunoProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[BrunoProgress], None]


@dataclass(frozen=True, slots=True)
class BrunoCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class BrunoTurn:
    species: int
    level: int
    enemy_hp: int
    lead_hp: int
    lead_status: int
    pp: tuple[int, int, int, int]
    move_slot: int


@dataclass(frozen=True, slots=True)
class BrunoChapterReport:
    records: tuple[BrunoCheckpoint, ...]
    final_raw: RawGameState
    turns: tuple[BrunoTurn, ...]
    party: tuple[tuple[int, int], ...]
    hyper_potions_used: int
    full_restores_used: int
    party_hp: tuple[int, int, int]
    party_max_hp: tuple[int, int, int]
    party_status: tuple[int, int, int]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == BRUNO_CHECKPOINT_COUNT
            and self.party == BRUNO_PARTY
            and _turns_valid(self.turns)
            and _event(self.final_raw, EventFlag.BEAT_BRUNO)
            and self.final_raw.map_id == MapId.AGATHAS_ROOM
            and self.final_raw.party_species_ids == TOWER_FINAL_PARTY
            and self.party_hp == self.party_max_hp
            and self.party_status == (0, 0, 0)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "defeat_bruno",
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
                }
                for item in self.turns
            ],
            "recovery": {
                "hyper_potions_used": self.hyper_potions_used,
                "full_restores_used": self.full_restores_used,
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


def run_bruno_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> BrunoChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[BrunoCheckpoint] = []
    initial = reader.read()
    if (
        initial.map_id != MapId.BRUNOS_ROOM
        or (initial.player_x, initial.player_y) != (4, 5)
        or initial.party_species_ids != TOWER_FINAL_PARTY
        or not _event(initial, EventFlag.BEAT_LORELEI)
        or _event(initial, EventFlag.BEAT_BRUNO)
    ):
        raise BrunoChapterError("Bruno input boundary is not qualified.")
    _checkpoint(records, progress, emulator, initial, "bruno_ready", "Bruno room ready")
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=BRUNO_RNG_DELAY_FRAMES))
    _teach_mega_punch(actions, reader, emulator)

    _move(actions, reader, BRUNO_APPROACH, "Bruno approach")
    _pulse(actions, MacroActionKind.INTERACT)
    for _ in range(40):
        if reader.read().battle_state == 2:
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise BrunoChapterError("Bruno battle did not start.")
    _checkpoint(records, progress, emulator, reader.read(), "bruno_engaged", "Engaged Bruno")

    turns: list[BrunoTurn] = []

    class _HealBoundary(Exception):
        pass

    last_recovery_turn = -1

    def policy(raw: RawGameState) -> int:
        hp = raw.first_party_hp or 0
        status = raw.first_party_status or 0
        if recovery_action_due(
            hp=hp,
            status=status,
            safe_hp=_bruno_recovery_threshold(raw),
            decisions_made=len(turns),
            last_recovery_decision=last_recovery_turn,
        ):
            raise _HealBoundary
        species = raw.enemy_species_id or 0
        pp = raw.first_party_pp or (0, 0, 0, 0)
        if species == 0x22 and pp[3] > BRUNO_LANCE_SURF_RESERVE:
            slot = 4
        elif species == 0x22 and pp[2] > 0:
            slot = 3
        elif pp[0] > 0:
            slot = 1
        elif pp[1] > 0:
            slot = 2
        elif pp[2] > 0:
            slot = 3
        else:
            slot = 4
        turns.append(
            BrunoTurn(
                species,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                hp,
                status,
                raw.first_party_pp or (0, 0, 0, 0),
                slot,
            )
        )
        return slot

    hyper_before = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    restore_before = _bag(emulator).get(ItemId.FULL_RESTORE, 0)
    while reader.read().battle_state:
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                policy,
                expected_map=MapId.BRUNOS_ROOM,
                intent=BattleIntent(
                    "defeat_bruno",
                    battle_plan_id=RedBattlePlanId.LEAGUE_BRUNO,
                    resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
                ),
                timing=BattleRuntimeTiming(max_runtime_pulses=1200),
                label="Bruno",
            )
        except BattleRuntimeError as error:
            if not isinstance(error.__cause__, _HealBoundary):
                current = reader.read()
                raise BrunoChapterError(
                    "Bruno battle runtime failed: "
                    f"party_hp={_party_hp(emulator)!r}, "
                    f"enemy={(current.enemy_species_id, current.enemy_hp, current.enemy_level)!r}, "
                    f"lead_status={current.first_party_status!r}, "
                    f"pp={current.first_party_pp!r}, "
                    f"bag={_bag(emulator)!r}, turns={turns!r}."
                ) from error
            raw = reader.read()
            if (raw.first_party_status or 0) and (raw.first_party_hp or 0) >= BRUNO_SAFE_HP:
                item = ItemId.FULL_HEAL
            elif raw.first_party_status or 0:
                item = ItemId.FULL_RESTORE
            else:
                item = (
                    ItemId.HYPER_POTION
                    if _bag(emulator).get(ItemId.HYPER_POTION, 0)
                    else ItemId.FULL_RESTORE
                )
            if _bag(emulator).get(item, 0) == 0:
                raise BrunoChapterError("Bruno exhausted the recovery reserve.") from error
            try:
                _battle_healing_item(
                    reader,
                    actions,
                    emulator,
                    DEFAULT_SILPH_TIMING,
                    item,
                )
            except SilphChapterError as healing_error:
                raise BrunoChapterError("Bruno recovery failed.") from healing_error
            last_recovery_turn = len(turns)

    for _ in range(5):
        _pulse(actions, MacroActionKind.CONFIRM)
    _settle_confirm(actions, reader, 40)
    if _party_hp(emulator) != _party_max_hp(emulator) or _party_status(emulator) != (0, 0, 0):
        try:
            item = (
                ItemId.FULL_RESTORE
                if _party_hp(emulator)[0] < _party_max_hp(emulator)[0]
                else ItemId.FULL_HEAL
            )
            _use_bag_item(
                actions,
                reader,
                emulator,
                DEFAULT_LAVENDER_TIMING,
                item,
            )
        except Exception as error:
            raise BrunoChapterError("Post-Bruno recovery failed.") from error
    defeated = reader.read()
    if not _event(defeated, EventFlag.BEAT_BRUNO):
        raise BrunoChapterError("Bruno event did not set after battle.")
    _checkpoint(records, progress, emulator, defeated, "bruno_defeated", "Defeated Bruno")

    _move(actions, reader, ("left", "up", "up", "up", "up"), "Agatha room entry")
    final = reader.read()
    report = BrunoChapterReport(
        records=tuple(records),
        final_raw=final,
        turns=tuple(turns),
        party=_encounter_party(turns),
        hyper_potions_used=hyper_before - _bag(emulator).get(ItemId.HYPER_POTION, 0),
        full_restores_used=restore_before - _bag(emulator).get(ItemId.FULL_RESTORE, 0),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise BrunoChapterError(f"Bruno terminal evidence failed: {report!r}.")
    return report


def _checkpoint(
    records: list[BrunoCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(BrunoCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            BrunoProgress(
                checkpoint_id,
                label,
                len(records),
                BRUNO_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _encounter_party(turns: Iterable[BrunoTurn]) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    for turn in turns:
        identity = (turn.species, turn.level)
        if not result or result[-1] != identity:
            result.append(identity)
    return tuple(result)


def _turns_valid(turns: Iterable[BrunoTurn]) -> bool:
    items = tuple(turns)
    return bool(items) and all(
        item.move_slot in {1, 2, 3, 4} and item.lead_hp > 0 and item.lead_status == 0
        for item in items
    )


def _bruno_recovery_threshold(raw: RawGameState) -> int:
    if raw.enemy_species_id == 0x7E:
        # Machamp's high-roll Submission can exceed the generic margin from
        # otherwise healthy HP.  The stocked Hyper Potions make a full-health
        # boundary safer than accepting a one-turn knockout window.
        return raw.first_party_max_hp or BRUNO_HITMONLEE_SAFE_HP
    if raw.enemy_species_id == 0x2B:
        return BRUNO_HITMONLEE_SAFE_HP
    return BRUNO_SAFE_HP


def _teach_mega_punch(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    expected_remaining: int = 1,
    expected_moves: tuple[int, int, int, int] = (0x05, 0x46, 0x3A, 0x39),
    replacement_slot: int = 0,
) -> None:
    _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
    _select_bag_item(
        actions,
        emulator,
        ItemId.TM01_MEGA_PUNCH,
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
        raise BrunoChapterError("TM01 did not reach party selection.")
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
        raise BrunoChapterError("TM01 did not reach move deletion.")
    for _ in range(replacement_slot):
        _pulse(actions, MacroActionKind.MOVE, "down")
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        raw = reader.read()
        if (
            raw.first_party_moves == expected_moves
            and _bag(emulator).get(ItemId.TM01_MEGA_PUNCH, 0) == expected_remaining
        ):
            _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise BrunoChapterError(
        "TM01 did not install the expected move set: "
        f"actual={reader.read().first_party_moves!r}, expected={expected_moves!r}, "
        f"remaining={_bag(emulator).get(ItemId.TM01_MEGA_PUNCH, 0)!r}, "
        f"expected_remaining={expected_remaining!r}."
    )
