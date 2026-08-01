"""Qualified Gold Teeth, HM04, and Strength chapter."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.celadon import _bag, _money, _party_hp, _party_max_hp, _party_status
from pokemon_red_completion.observation import (
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.tower import party_core_intact

STRENGTH_CHECKPOINT_COUNT = 8
TAIL_WHIP = 0x27
STRENGTH = 0x46
EXPECTED_MOVES_BEFORE = (0x2C, TAIL_WHIP, 0x3D, 0x39)
EXPECTED_MOVES_AFTER = (0x2C, STRENGTH, 0x3D, 0x39)
EXPECTED_PP_AFTER = (25, 15, 20, 15)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[item] for item in value)


CENTER_EXIT = ("down",) * 5
CITY_TO_WARDEN = _directions(
    "RRRUURUUUUUUUUUURDRRRRDRURRRRRRURRRDLLDLLLDRRDLDRDLDRDLDRDLLDRRDLDRDLLLLLUULLLLU"
)
HOUSE_TO_WARDEN = _directions("UUURRUUULLLLDRD")
WARDEN_TO_HOUSE = _directions("ULURRRRDDDLLDDD")
WARDEN_TO_CITY_CENTER = _directions(
    "DRRRRDDRRRRRULURULLURRULURULURULURULLURRRURRULLLDLLLLLLDLULLLLULDDDDDDDDDD"
    "UUUUUUUUUULUULDDLLDRRRDLLLDRRRDLLLLLLLLLLLLLLLLLLLLUUUULLLDRRDLDRDL"
    "DDDDDDDDDDDDRRRRRRRUUUURRRRRRRRRRRU"
)
CENTER_TO_NURSE = ("up",) * 4


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class StrengthChapterError(RuntimeError):
    """Raised when the HM04 evidence contract fails."""


@dataclass(frozen=True, slots=True)
class StrengthTiming:
    wait_frames: int = 240
    movement_frames: int = 240
    movement_retries: int = 18
    dialogue_pulses: int = 36
    menu_pulses: int = 24
    heal_pulses: int = 20

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_STRENGTH_TIMING = StrengthTiming()


@dataclass(frozen=True, slots=True)
class StrengthProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[StrengthProgress], None]


@dataclass(frozen=True, slots=True)
class StrengthCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class StrengthChapterReport:
    records: tuple[StrengthCheckpoint, ...]
    final_raw: RawGameState
    initial_bag: tuple[tuple[int, int], ...]
    final_bag: tuple[tuple[int, int], ...]
    initial_money: int
    final_money: int
    gave_gold_teeth: bool
    got_hm04: bool
    gold_teeth_removed: bool
    hm04_retained: bool
    moves_before: tuple[int, ...]
    moves_after: tuple[int, ...]
    pp_after: tuple[int, ...]
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        without_teeth = tuple(
            (item, count)
            for item, count in self.initial_bag
            if item != int(ItemId.GOLD_TEETH)
        )
        expected_bag = tuple(
            sorted((*without_teeth, (int(ItemId.HM04_STRENGTH), 1)))
        )
        return (
            len(self.records) == STRENGTH_CHECKPOINT_COUNT
            and self.gave_gold_teeth
            and self.got_hm04
            and self.gold_teeth_removed
            and self.hm04_retained
            and self.final_bag == expected_bag
            and self.initial_money >= 0
            and self.final_money == self.initial_money
            and self.moves_before == EXPECTED_MOVES_BEFORE
            and self.moves_after == EXPECTED_MOVES_AFTER
            and self.pp_after == EXPECTED_PP_AFTER
            and self.final_raw.map_id == MapId.FUCHSIA_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and all(status == 0 for status in self.party_status)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "obtain_strength",
            "warden": {
                "gold_teeth_removed": self.gold_teeth_removed,
                "gave_gold_teeth_event": self.gave_gold_teeth,
                "got_hm04_event": self.got_hm04,
                "hm04_reusable_and_retained": self.hm04_retained,
            },
            "strength": {
                "move_id": STRENGTH,
                "replaced_move_id": TAIL_WHIP,
                "slot": 2,
                "moves_before": list(self.moves_before),
                "moves_after": list(self.moves_after),
                "pp_after": list(self.pp_after),
            },
            "money_remaining": self.final_money,
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


class _CountingExecutor:
    def __init__(self, executor: ChapterExecutor) -> None:
        self._executor = executor
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> object:
        result = self._executor.execute(action)
        self.actions_executed += 1
        return result


def run_strength_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: StrengthTiming = DEFAULT_STRENGTH_TIMING,
    progress: ProgressSink | None = None,
) -> StrengthChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[StrengthCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.FUCHSIA_POKECENTER, (3, 3), "Koga boundary")
    initial_bag = _bag_tuple(emulator)
    initial_money = _money(emulator)
    moves_before = tuple(initial.first_party_moves or ())
    if (
        moves_before != EXPECTED_MOVES_BEFORE
        or ItemId.GOLD_TEETH not in _bag(emulator)
        or ItemId.HM04_STRENGTH in _bag(emulator)
        or _event(emulator, EventFlag.GOT_HM04)
        or _event(emulator, EventFlag.GAVE_GOLD_TEETH)
    ):
        raise StrengthChapterError("Strength input boundary is not pristine.")
    _checkpoint(records, progress, emulator, initial, "strength_ready", "Gold Teeth ready")

    _move(actions, reader, CENTER_EXIT, timing, "Fuchsia Center exit")
    _move(actions, reader, CITY_TO_WARDEN, timing, "Warden house route")
    _require(reader.read(), MapId.WARDENS_HOUSE, (4, 7), "Warden house entry")
    _checkpoint(records, progress, emulator, reader.read(), "warden_house", "Entered Warden house")

    _move(actions, reader, HOUSE_TO_WARDEN, timing, "Warden approach")
    _require(reader.read(), MapId.WARDENS_HOUSE, (3, 3), "Warden stance")
    _checkpoint(records, progress, emulator, reader.read(), "warden_stance", "Reached Warden")
    _pulse(actions, MacroActionKind.MOVE, "left", frames=timing.wait_frames)
    actions.execute(MacroAction(MacroActionKind.INTERACT))

    for _ in range(timing.dialogue_pulses):
        if _event(emulator, EventFlag.GAVE_GOLD_TEETH):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise StrengthChapterError("Warden did not accept the Gold Teeth.")
    if ItemId.GOLD_TEETH in _bag(emulator):
        raise StrengthChapterError("Gold Teeth event set without removing the item.")
    _checkpoint(records, progress, emulator, reader.read(), "teeth_given", "Returned Gold Teeth")

    for _ in range(timing.dialogue_pulses):
        if _event(emulator, EventFlag.GOT_HM04) and ItemId.HM04_STRENGTH in _bag(emulator):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise StrengthChapterError("Warden did not award reusable HM04.")
    _checkpoint(records, progress, emulator, reader.read(), "hm04", "Received reusable HM04")
    for _ in range(6):
        _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)

    _teach_strength(actions, reader, emulator, timing)
    _checkpoint(records, progress, emulator, reader.read(), "strength", "Taught Strength")

    _move(actions, reader, WARDEN_TO_HOUSE, timing, "Warden house exit route")
    _move(actions, reader, WARDEN_TO_CITY_CENTER, timing, "Fuchsia Center return")
    _require(reader.read(), MapId.FUCHSIA_POKECENTER, (3, 7), "Center entrance")
    _checkpoint(records, progress, emulator, reader.read(), "center_return", "Returned to Center")
    _move(actions, reader, CENTER_TO_NURSE, timing, "Fuchsia nurse")
    _heal(actions, reader, emulator, timing)
    final = reader.read()
    _require(final, MapId.FUCHSIA_POKECENTER, (3, 3), "stable Strength boundary")
    _checkpoint(records, progress, emulator, final, "strength_stable", "Stable healed boundary")

    report = StrengthChapterReport(
        tuple(records),
        final,
        initial_bag,
        _bag_tuple(emulator),
        initial_money,
        _money(emulator),
        _event(emulator, EventFlag.GAVE_GOLD_TEETH),
        _event(emulator, EventFlag.GOT_HM04),
        ItemId.GOLD_TEETH not in _bag(emulator),
        ItemId.HM04_STRENGTH in _bag(emulator),
        moves_before,
        tuple(final.first_party_moves or ()),
        tuple(final.first_party_pp or ()),
        _party_hp(emulator),
        _party_max_hp(emulator),
        _party_status(emulator),
        emulator.frame_count - start_frames,
        actions.actions_executed,
        not emulator.pressed_buttons,
    )
    if not report.passed:
        raise StrengthChapterError(
            f"Strength chapter failed its public evidence contract: {report.public_dict()!r}."
        )
    return report


def _teach_strength(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: StrengthTiming,
) -> None:
    actions.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(actions, timing.wait_frames)
    _select_cursor(actions, emulator, 2, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _select_bag_item(actions, emulator, ItemId.HM04_STRENGTH, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.menu_pulses):
        if _menu_origin(emulator) == (0, 1):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise StrengthChapterError("HM04 did not reach party selection.")
    _select_cursor(actions, emulator, 0, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.menu_pulses):
        if _menu_origin(emulator) == (5, 8):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise StrengthChapterError("HM04 did not reach move deletion.")
    _select_cursor(actions, emulator, 1, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.menu_pulses):
        raw = reader.read()
        if (
            raw.first_party_moves == EXPECTED_MOVES_AFTER
            and raw.first_party_pp == EXPECTED_PP_AFTER
            and ItemId.HM04_STRENGTH in _bag(emulator)
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise StrengthChapterError("HM04 did not replace slot-two Tail Whip.")
    for _ in range(4):
        _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)


def _move(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    timing: StrengthTiming,
    label: str,
) -> None:
    state = reader.read()
    for step, direction in enumerate(directions, 1):
        before = (state.map_id, state.player_x, state.player_y)
        for _ in range(timing.movement_retries):
            _pulse(actions, MacroActionKind.MOVE, direction, frames=timing.movement_frames)
            state = reader.read()
            if state.battle_state:
                raise StrengthChapterError(f"{label} entered an unexpected battle.")
            if (state.map_id, state.player_x, state.player_y) != before:
                break
            if not reader.read_input_readiness().ready:
                _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
                state = reader.read()
        else:
            raise StrengthChapterError(
                f"{label} blocked at step {step}: {direction}; "
                f"{(state.map_id, state.player_x, state.player_y)!r}."
            )
        if not party_core_intact(state.party_species_ids):
            raise StrengthChapterError(f"{label} changed the qualified party.")


def _heal(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: StrengthTiming,
) -> None:
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    for _ in range(timing.heal_pulses):
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and all(status == 0 for status in _party_status(emulator))
            and reader.read().first_party_pp == EXPECTED_PP_AFTER
        ):
            for _ in range(6):
                _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
            return
    raise StrengthChapterError("Fuchsia Center did not restore the Strength boundary.")


def _select_cursor(
    actions: _CountingExecutor,
    emulator: EmulatorState,
    target: int,
    timing: StrengthTiming,
) -> None:
    for _ in range(16):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target:
            return
        direction = "down" if cursor < target else "up"
        _pulse(actions, MacroActionKind.MOVE, direction, frames=timing.wait_frames)
    raise StrengthChapterError(f"Menu cursor did not reach {target}.")


def _select_bag_item(
    actions: _CountingExecutor,
    emulator: EmulatorState,
    item: ItemId,
    timing: StrengthTiming,
) -> None:
    for _ in range(32):
        bag = list(_bag(emulator))
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        if absolute < len(bag) and bag[absolute] == item:
            return
        _pulse(
            actions,
            MacroActionKind.MOVE,
            "down",
            frames=min(timing.wait_frames, 120),
        )
    raise StrengthChapterError(f"Bag cursor did not reach item {int(item):#x}.")


def _menu_origin(emulator: EmulatorState) -> tuple[int, int]:
    return (
        emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
        emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
    )


def _event(emulator: EmulatorState, event: EventFlag) -> bool:
    value = int(event)
    return bool(
        emulator.read_u8(int(RamAddress.EVENT_FLAGS) + value // 8)
        & (1 << (value % 8))
    )


def _bag_tuple(emulator: EmulatorState) -> tuple[tuple[int, int], ...]:
    return tuple(
        sorted((int(item), count) for item, count in Counter(_bag(emulator)).items())
    )


def _require(
    raw: RawGameState,
    map_id: int,
    coordinate: tuple[int, int],
    label: str,
) -> None:
    if (
        raw.map_id != map_id
        or (raw.player_x, raw.player_y) != coordinate
        or raw.battle_state != 0
        or not party_core_intact(raw.party_species_ids)
    ):
        raise StrengthChapterError(
            f"{label} missed gate: map={raw.map_id!r}, "
            f"coordinate={(raw.player_x, raw.player_y)!r}."
        )


def _checkpoint(
    records: list[StrengthCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(StrengthCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            StrengthProgress(
                checkpoint_id,
                label,
                len(records),
                STRENGTH_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _wait(actions: _CountingExecutor, frames: int) -> None:
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _pulse(
    actions: _CountingExecutor,
    kind: MacroActionKind,
    value: str | int | None = None,
    *,
    frames: int,
) -> None:
    actions.execute(MacroAction(kind, value))
    _wait(actions, frames)
