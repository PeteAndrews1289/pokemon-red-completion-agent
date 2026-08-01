"""Qualified Celadon vending-machine route and Saffron access chapter."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.celadon import (
    DEFAULT_CELADON_TIMING,
    CeladonChapterError,
    _bag,
    _flee,
    _money,
    _party_hp,
    _party_max_hp,
    _party_status,
    _RunState,
)
from pokemon_red_completion.observation import (
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.tower import TOWER_FINAL_PARTY

SAFFRON_CHECKPOINT_COUNT = 8
FRESH_WATER_PRICE = 200
GUARD_DRINK_FLAG = 0x40


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[c] for c in value)


CENTER_EXIT = _directions("DDDDD")
CITY_TO_MART = _directions("DDDLLLLLLLLLLLLLLLLLLLLLLDLLLLLLLLLU")
MART_1F_TO_2F = _directions("UUUULULLLU")
MART_2F_TO_3F = _directions("LLLDDDRRRRRURUURU")
MART_3F_TO_4F = _directions("LLLLU")
MART_4F_TO_5F = _directions("RRRRU")
MART_5F_TO_ROOF = _directions("LLLLU")
ROOF_TO_VENDING = _directions("LLL")
ROOF_TO_5F = _directions("RRRU")
MART_5F_TO_4F = _directions("RRRRU")
MART_4F_TO_3F = _directions("LLLLU")
MART_3F_TO_2F = _directions("RRRRU")
MART_2F_TO_1F = _directions("LLLLU")
MART_TO_CITY = _directions("RRRDRDDDDD")
CITY_TO_ROUTE_7 = ("right",) * 4 + ("up",) * 3 + ("right",) * 36
ROUTE_7_TO_GATE = _directions("RRRRRRRRRDDDDDDDRR")
GATE_TO_SAFFRON = ("right",) * 6
SAFFRON_TO_CENTER = ("right",) * 2 + ("down",) * 12 + ("right",) * 6 + ("up",)


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class SaffronChapterError(RuntimeError):
    """Raised when the Saffron-access evidence contract fails."""


@dataclass(frozen=True, slots=True)
class SaffronTiming:
    movement_frames: int = 240
    movement_retries: int = 8
    vending_pulses: int = 12
    guard_pulses: int = 160
    heal_pulses: int = 24

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_SAFFRON_TIMING = SaffronTiming()


@dataclass(frozen=True, slots=True)
class SaffronProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[SaffronProgress], None]


@dataclass(frozen=True, slots=True)
class SaffronCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class SaffronChapterReport:
    records: tuple[SaffronCheckpoint, ...]
    final_raw: RawGameState
    money_before: int
    money_after_purchase: int
    money_after: int
    vending_cursor: int
    fresh_water_before: int
    fresh_water_after_purchase: int
    fresh_water_after_guard: int
    guard_flag_before: int
    guard_flag_after_consumption: int
    guard_flag_after_dialogue: int
    bag_before: tuple[tuple[int, int], ...]
    bag_after: tuple[tuple[int, int], ...]
    party_hp: tuple[int, int, int]
    party_max_hp: tuple[int, int, int]
    party_status: tuple[int, int, int]
    battle_free: bool
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        final_bag = dict(self.bag_after)
        return (
            len(self.records) == SAFFRON_CHECKPOINT_COUNT
            and self.money_before >= FRESH_WATER_PRICE
            and self.money_after_purchase
            == self.money_after
            == self.money_before - FRESH_WATER_PRICE
            and self.vending_cursor == 0
            and self.fresh_water_before == 0
            and self.fresh_water_after_purchase == 1
            and self.fresh_water_after_guard == 0
            and self.guard_flag_before & GUARD_DRINK_FLAG == 0
            and self.guard_flag_after_consumption & GUARD_DRINK_FLAG == 0
            and self.guard_flag_after_dialogue & GUARD_DRINK_FLAG
            and self.bag_before == self.bag_after
            and int(ItemId.FRESH_WATER) not in final_bag
            and int(ItemId.SODA_POP) not in final_bag
            and int(ItemId.LEMONADE) not in final_bag
            and self.final_raw.map_id == MapId.SAFFRON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.battle_state == 0
            and self.final_raw.party_species_ids == TOWER_FINAL_PARTY
            and self.final_raw.first_party_level is not None
            and 42 <= self.final_raw.first_party_level <= 43
            and self.final_raw.first_party_moves == (0x82, 0x46, 0x3A, 0x39)
            and self.final_raw.first_party_pp == (15, 15, 10, 15)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and self.final_raw.first_party_hp == self.party_hp[0]
            and self.final_raw.first_party_max_hp == self.party_max_hp[0]
            and self.party_status == (0, 0, 0)
            and self.battle_free
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "reach_saffron",
            "vending_machine": {
                "floor": "celadon_mart_roof",
                "cursor": self.vending_cursor,
                "item_id": int(ItemId.FRESH_WATER),
                "price": FRESH_WATER_PRICE,
                "money_before": self.money_before,
                "money_after": self.money_after_purchase,
            },
            "guard_handoff": {
                "fresh_water": [
                    self.fresh_water_before,
                    self.fresh_water_after_purchase,
                    self.fresh_water_after_guard,
                ],
                "flag_before": self.guard_flag_before,
                "flag_after_consumption": self.guard_flag_after_consumption,
                "flag_after_dialogue": self.guard_flag_after_dialogue,
                "consumed_before_global_access": True,
            },
            "other_guard_drinks_absent": {
                "soda_pop": int(ItemId.SODA_POP) not in dict(self.bag_after),
                "lemonade": int(ItemId.LEMONADE) not in dict(self.bag_after),
            },
            "party": {
                "lead_level": self.final_raw.first_party_level,
                "hp": list(self.party_hp),
                "max_hp": list(self.party_max_hp),
                "status": list(self.party_status),
                "moves": list(self.final_raw.first_party_moves or ()),
                "pp": list(self.final_raw.first_party_pp or ()),
            },
            "battle_free": self.battle_free,
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


def run_saffron_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: SaffronTiming = DEFAULT_SAFFRON_TIMING,
    progress: ProgressSink | None = None,
) -> SaffronChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[SaffronCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.CELADON_POKECENTER, (3, 3), "Erika boundary")
    initial_bag = _bag(emulator)
    initial_money = _money(emulator)
    initial_flag = emulator.read_u8(RamAddress.STATUS_FLAGS_1)
    if (
        initial_money < FRESH_WATER_PRICE
        or initial_bag.get(ItemId.FRESH_WATER, 0)
        or initial_bag.get(ItemId.SODA_POP, 0)
        or initial_bag.get(ItemId.LEMONADE, 0)
        or initial_flag & GUARD_DRINK_FLAG
    ):
        raise SaffronChapterError("Saffron input boundary is not pristine.")
    _checkpoint(records, progress, emulator, initial, "saffron_ready", "Rainbow boundary ready")

    legs = (
        (CENTER_EXIT, MapId.CELADON_CITY, (41, 10), "center_exit"),
        (CITY_TO_MART, MapId.CELADON_MART_1F, (16, 7), "mart_1f"),
        (MART_1F_TO_2F, MapId.CELADON_MART_2F, (12, 2), "mart_2f"),
        (MART_2F_TO_3F, MapId.CELADON_MART_3F, (16, 2), "mart_3f"),
        (MART_3F_TO_4F, MapId.CELADON_MART_4F, (12, 2), "mart_4f"),
        (MART_4F_TO_5F, MapId.CELADON_MART_5F, (16, 2), "mart_5f"),
        (MART_5F_TO_ROOF, MapId.CELADON_MART_ROOF, (15, 3), "mart_roof"),
    )
    for route, map_id, coordinate, label in legs:
        _move(actions, reader, emulator, route, timing, label)
        _require(reader.read(), map_id, coordinate, label)
    _checkpoint(records, progress, emulator, reader.read(), "roof_reached", "Reached vending roof")

    _move(actions, reader, emulator, ROOF_TO_VENDING, timing, "vending stance")
    _require(reader.read(), MapId.CELADON_MART_ROOF, (12, 3), "vending stance")
    actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
    _wait(actions, timing.movement_frames)
    _require(reader.read(), MapId.CELADON_MART_ROOF, (12, 3), "vending facing")
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(actions, timing.movement_frames)
    vending_cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
    if vending_cursor != 0:
        raise SaffronChapterError(f"Fresh Water was not vending cursor zero: {vending_cursor}.")
    for _ in range(timing.vending_pulses):
        if (
            _money(emulator) == initial_money - FRESH_WATER_PRICE
            and _bag(emulator).get(ItemId.FRESH_WATER, 0) == 1
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=1)
    else:
        raise SaffronChapterError("Fresh Water purchase did not settle.")
    money_after_purchase = _money(emulator)
    fresh_water_after_purchase = _bag(emulator).get(ItemId.FRESH_WATER, 0)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    if not reader.read_input_readiness().ready:
        raise SaffronChapterError("Vending delivery dialogue did not close.")
    _checkpoint(records, progress, emulator, reader.read(), "water_bought", "Bought Fresh Water")

    return_legs = (
        (ROOF_TO_5F, MapId.CELADON_MART_5F, (12, 2), "roof_return"),
        (MART_5F_TO_4F, MapId.CELADON_MART_4F, (16, 2), "mart_4f_return"),
        (MART_4F_TO_3F, MapId.CELADON_MART_3F, (12, 2), "mart_3f_return"),
        (MART_3F_TO_2F, MapId.CELADON_MART_2F, (16, 2), "mart_2f_return"),
        (MART_2F_TO_1F, MapId.CELADON_MART_1F, (12, 2), "mart_1f_return"),
        (MART_TO_CITY, MapId.CELADON_CITY, (10, 14), "mart_exit"),
        (CITY_TO_ROUTE_7, MapId.ROUTE_7, (0, 3), "route_7"),
        (ROUTE_7_TO_GATE, MapId.ROUTE_7_GATE, (0, 4), "route_7_gate"),
    )
    for route, map_id, coordinate, label in return_legs:
        _move(actions, reader, emulator, route, timing, label)
        _require(reader.read(), map_id, coordinate, label)
    _checkpoint(records, progress, emulator, reader.read(), "gate_reached", "Reached Route 7 guard")

    _move(actions, reader, emulator, ("right", "right"), timing, "guard approach")
    _require(reader.read(), MapId.ROUTE_7_GATE, (2, 4), "guard approach")
    if _bag(emulator).get(ItemId.FRESH_WATER, 0) != 1:
        raise SaffronChapterError("Fresh Water missing before guard trigger.")
    _move(
        actions,
        reader,
        emulator,
        ("right",),
        timing,
        "guard trigger",
        allow_script=True,
    )
    _require(reader.read(), MapId.ROUTE_7_GATE, (3, 4), "guard trigger")
    fresh_water_after_guard = _bag(emulator).get(ItemId.FRESH_WATER, 0)
    flag_after_consumption = emulator.read_u8(RamAddress.STATUS_FLAGS_1)
    if fresh_water_after_guard or flag_after_consumption & GUARD_DRINK_FLAG:
        raise SaffronChapterError("Guard handoff ordering was not item-before-flag.")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "drink_consumed",
        "Guard consumed drink before access flag",
    )

    for _ in range(timing.guard_pulses):
        flag = emulator.read_u8(RamAddress.STATUS_FLAGS_1)
        if flag & GUARD_DRINK_FLAG and reader.read_input_readiness().ready:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=1)
    else:
        raise SaffronChapterError("Guard dialogue did not grant global Saffron access.")
    final_flag = emulator.read_u8(RamAddress.STATUS_FLAGS_1)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "guards_bribed",
        "Global guard access set",
    )

    _move(actions, reader, emulator, GATE_TO_SAFFRON, timing, "Saffron crossing")
    _require(reader.read(), MapId.SAFFRON_CITY, (1, 18), "Saffron entry")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "saffron_entered",
        "Entered Saffron City",
    )

    _move(actions, reader, emulator, SAFFRON_TO_CENTER, timing, "Saffron Center")
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "Saffron Center entry")
    _move(actions, reader, emulator, ("up",) * 4, timing, "Saffron nurse")
    for _ in range(9):
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    for _ in range(timing.heal_pulses):
        raw = reader.read()
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and _party_status(emulator) == (0, 0, 0)
            and raw.first_party_pp == (15, 15, 10, 15)
            and reader.read_input_readiness().ready
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=1)
    else:
        raise SaffronChapterError("Saffron Center healing did not settle.")
    final = reader.read()
    _checkpoint(records, progress, emulator, final, "saffron_stable", "Healed Saffron boundary")

    report = SaffronChapterReport(
        records=tuple(records),
        final_raw=final,
        money_before=initial_money,
        money_after_purchase=money_after_purchase,
        money_after=_money(emulator),
        vending_cursor=vending_cursor,
        fresh_water_before=initial_bag.get(ItemId.FRESH_WATER, 0),
        fresh_water_after_purchase=fresh_water_after_purchase,
        fresh_water_after_guard=fresh_water_after_guard,
        guard_flag_before=initial_flag,
        guard_flag_after_consumption=flag_after_consumption,
        guard_flag_after_dialogue=final_flag,
        bag_before=tuple(sorted(initial_bag.items())),
        bag_after=tuple(sorted(_bag(emulator).items())),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        battle_free=final.battle_state == 0,
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise SaffronChapterError(f"Saffron evidence contract failed: {report.public_dict()!r}.")
    return report


def _move(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    route: Iterable[str],
    timing: SaffronTiming,
    label: str,
    *,
    allow_script: bool = False,
) -> None:
    for index, direction in enumerate(tuple(route), 1):
        before = reader.read()
        for _ in range(timing.movement_retries):
            actions.execute(MacroAction(MacroActionKind.MOVE, direction))
            _wait(actions, timing.movement_frames)
            after = reader.read()
            if after.battle_state == 1:
                try:
                    _flee(
                        actions,  # type: ignore[arg-type]
                        reader,
                        emulator,
                        _RunState([]),
                        DEFAULT_CELADON_TIMING,
                    )
                except CeladonChapterError as error:
                    raise SaffronChapterError(
                        f"{label} could not recover from a wild battle: {error}"
                    ) from error
                after = reader.read()
            if after.battle_state == 2:
                raise SaffronChapterError(f"{label} entered an unexpected trainer battle.")
            moved = (
                after.map_id != before.map_id
                or after.player_x != before.player_x
                or after.player_y != before.player_y
            )
            if moved or (allow_script and not reader.read_input_readiness().ready):
                break
        else:
            raise SaffronChapterError(
                f"{label} blocked at step {index}: {direction}; "
                f"{(after.map_id, after.player_x, after.player_y)!r}."
            )


def _pulse(
    actions: _CountingExecutor,
    kind: MacroActionKind,
    *,
    frames: int,
) -> None:
    actions.execute(MacroAction(kind))
    _wait(actions, frames)


def _wait(actions: _CountingExecutor, frames: int) -> None:
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _require(raw: RawGameState, map_id: MapId, coordinate: tuple[int, int], label: str) -> None:
    if (
        raw.map_id != map_id
        or (raw.player_x, raw.player_y) != coordinate
        or raw.battle_state != 0
    ):
        raise SaffronChapterError(
            f"{label} mismatch: {(raw.map_id, raw.player_x, raw.player_y, raw.battle_state)!r}."
        )


def _checkpoint(
    records: list[SaffronCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(SaffronCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            SaffronProgress(
                checkpoint_id=checkpoint_id,
                label=label,
                completed=len(records),
                total=SAFFRON_CHECKPOINT_COUNT,
                frames_executed=emulator.frame_count,
            )
        )
