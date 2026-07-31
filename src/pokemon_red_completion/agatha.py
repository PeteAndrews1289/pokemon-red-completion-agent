"""Qualified Agatha chapter for the pinned Pokémon Red runtime."""

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

AGATHA_CHECKPOINT_COUNT = 3
AGATHA_RNG_DELAY_FRAMES = 85
AGATHA_SAFE_HP = 100
AGATHA_PARTY = (
    (0x0E, 56),
    (0x82, 56),
    (0x93, 55),
    (0x2D, 58),
    (0x0E, 60),
)
AGATHA_APPROACH = ("right", "up", "up")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


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


@dataclass(frozen=True, slots=True)
class AgathaChapterReport:
    records: tuple[AgathaCheckpoint, ...]
    final_raw: RawGameState
    turns: tuple[AgathaTurn, ...]
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
            len(self.records) == AGATHA_CHECKPOINT_COUNT
            and self.party == AGATHA_PARTY
            and _turns_valid(self.turns)
            and _event(self.final_raw, EventFlag.BEAT_AGATHA)
            and self.final_raw.map_id == MapId.LANCES_ROOM
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
            "objective": "defeat_agatha",
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
    actions = _CountingExecutor(executor)
    records: list[AgathaCheckpoint] = []
    initial = reader.read()
    if (
        initial.map_id != MapId.AGATHAS_ROOM
        or (initial.player_x, initial.player_y) != (4, 5)
        or initial.party_species_ids != TOWER_FINAL_PARTY
        or not _event(initial, EventFlag.BEAT_BRUNO)
        or _event(initial, EventFlag.BEAT_AGATHA)
    ):
        raise AgathaChapterError("Agatha input boundary is not qualified.")
    _checkpoint(records, progress, emulator, initial, "agatha_ready", "Agatha room ready")
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

    class _HealBoundary(Exception):
        pass

    def policy(raw: RawGameState) -> int:
        hp = raw.first_party_hp or 0
        status = raw.first_party_status or 0
        if hp < AGATHA_SAFE_HP or status:
            raise _HealBoundary
        pp = raw.first_party_pp or (0, 0, 0, 0)
        species = raw.enemy_species_id or 0
        if species in {0x82, 0x2D} and pp[0] > 0:
            slot = 1
        elif pp[3] > 0:
            slot = 4
        elif pp[2] > 0:
            slot = 3
        else:
            slot = 1
        turns.append(
            AgathaTurn(
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
    while reader.read().battle_state:
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                policy,
                expected_map=MapId.AGATHAS_ROOM,
                intent=BattleIntent(
                    "defeat_agatha",
                    battle_plan_id=RedBattlePlanId.LEAGUE_AGATHA,
                    resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
                ),
                timing=BattleRuntimeTiming(
                    max_runtime_pulses=2000,
                    max_sleep_recovery_pulses=96,
                    max_post_attack_transition_pulses=30,
                ),
                label="Agatha",
            )
        except BattleRuntimeError as error:
            if not isinstance(error.__cause__, _HealBoundary):
                raise AgathaChapterError("Agatha battle runtime failed.") from error
            raw = reader.read()
            if (
                (raw.first_party_status or 0)
                and (raw.first_party_hp or 0) >= 120
                and _bag(emulator).get(ItemId.FULL_HEAL, 0)
            ):
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
                raise AgathaChapterError("Agatha exhausted the recovery reserve.") from error
            try:
                _battle_healing_item(
                    reader,
                    actions,
                    emulator,
                    DEFAULT_SILPH_TIMING,
                    item,
                )
            except SilphChapterError as healing_error:
                current = reader.read()
                raise AgathaChapterError(
                    "Agatha recovery failed: "
                    f"party_hp={_party_hp(emulator)!r}, "
                    f"enemy={(current.enemy_species_id, current.enemy_hp, current.enemy_level)!r}, "
                    f"lead_status={current.first_party_status!r}, "
                    f"pp={current.first_party_pp!r}, bag={_bag(emulator)!r}."
                ) from healing_error

    for _ in range(20):
        _pulse(actions, MacroActionKind.CANCEL)
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
            raise AgathaChapterError("Post-Agatha recovery failed.") from error
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
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
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


def _turns_valid(turns: Iterable[AgathaTurn]) -> bool:
    items = tuple(turns)
    return bool(items) and all(
        item.move_slot in {1, 3, 4}
        and item.lead_hp >= AGATHA_SAFE_HP
        and item.lead_status == 0
        for item in items
    )


def _teach_take_down(
    actions: _CountingExecutor,
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
        raise AgathaChapterError("TM09 did not reach party selection.")
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
        raise AgathaChapterError("TM09 did not reach move deletion.")
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
    raise AgathaChapterError("TM09 did not install Take Down in the requested slot.")
