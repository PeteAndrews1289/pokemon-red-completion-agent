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
from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    LavenderChapterError,
    _buy_mart_item,
    _close_menus,
    _open_bag,
    _select_bag_item,
    _select_cursor,
)
from pokemon_red_completion.navigation import (
    Coordinate,
    GridMap,
    path_to_directions,
    shortest_path,
)
from pokemon_red_completion.observation import (
    SAFFRON_GUARD_ACCESS_MASK,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.tower import party_core_intact

SAFFRON_CHECKPOINT_COUNT = 10
SAFFRON_ACCESS_CHECKPOINT_COUNT = 8
FRESH_WATER_PRICE = 200
THUNDER_STONE_PRICE = 2100
GUARD_DRINK_FLAG = SAFFRON_GUARD_ACCESS_MASK
EEVEE = 0x66
JOLTEON = 0x68
ROOF_HOUSE_GRID = GridMap(
    width=8,
    height=8,
    blocked=frozenset(
        {
            *(Coordinate(x, 0) for x in range(8)),
            Coordinate(7, 1),
            Coordinate(3, 3),
            Coordinate(4, 3),
            Coordinate(3, 4),
            Coordinate(4, 4),
            Coordinate(0, 6),
            Coordinate(7, 6),
            Coordinate(0, 7),
            Coordinate(7, 7),
        }
    ),
)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[c] for c in value)


CENTER_EXIT = _directions("DDDDD")
CITY_TO_MANSION_REAR = _directions("RRRUUUUULLLLLLLLLLLLUUULLLLLLLLDDU")
MANSION_1F_REAR_STAIRS = _directions("L")
MANSION_2F_REAR_STAIRS = _directions("RR")
MANSION_3F_REAR_STAIRS = _directions("LL")
MANSION_ROOF_TO_HOUSE = _directions("RRDDDDDDLLU")
ROOF_HOUSE_TO_EEVEE = _directions("RRUURUUUL")
EEVEE_TO_ROOF_HOUSE_EXIT = _directions("RDDDLLLDDD")
MANSION_ROOF_TO_3F = _directions("RRUUUUUUULL")
MANSION_3F_TO_2F = _directions("RR")
MANSION_2F_TO_1F = _directions("LL")
MANSION_1F_TO_CITY = _directions("RRU")
MANSION_REAR_TO_CENTER_EXTERIOR_24 = _directions("RURRRRRRRRDDRRRRRRRRRRRDDDDDDLLL")
MANSION_REAR_TO_CENTER_EXTERIOR_25 = _directions("URRRRRRRRDDRRRRRRRRRRRDDDDDDLLL")
CITY_TO_MART = _directions("DDDLLLLLLLLLLLLLLLLLLLLLLDLLLLLLLLLU")
MART_1F_TO_2F = _directions("UUUULULLLU")
MART_2F_TO_3F = _directions("LLLDDDRRRRRURUURU")
MART_3F_TO_4F = _directions("LLLLU")
MART_4F_TO_STONE_CLERK = _directions("LLLLLLLLLLLDDDRRRR")
STONE_CLERK_WALKER_BLOCK_POSITIONS = ((2, 2), (4, 2))
STONE_CLERK_RETURN_BLOCK_POSITION = (5, 2)
STONE_CLERK_RETURN_RETREAT_POSITION = (1, 2)
STONE_CLERK_RETURN_YIELD_POSITION = (1, 3)
STONE_CLERK_RETURN_MAX_X = 11
STONE_CLERK_WALKER_CLEAR_ATTEMPTS = 64
STONE_CLERK_WALKER_Y = 0xC234
STONE_CLERK_WALKER_X = 0xC235
STONE_CLERK_RETURN_CLEAR_FRAMES = 2_048
MART_2F_GIRL_Y = 0xC244
MART_2F_GIRL_X = 0xC245
MART_2F_RETURN_BLOCK_POSITION = (15, 2)
MART_2F_RETURN_CLEAR_POSITION = (14, 2)
MART_2F_RETURN_CLEAR_FRAMES = 2_048
STONE_CLERK_TO_MART_4F_STAIRS = _directions("LLLLUUURRRRRRRRRRR")
MART_4F_TO_5F = _directions("RRRRU")
MART_5F_GENTLEMAN_BLOCK_POSITION = (15, 2)
MART_5F_GENTLEMAN_YIELD_POSITION = (15, 3)
MART_5F_GENTLEMAN_CLEAR_POSITION = (14, 2)
MART_5F_GENTLEMAN_CLEAR_ATTEMPTS = 16
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
    money_after_stone: int
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
    party_before: tuple[int, ...]
    party_after: tuple[int, ...]
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    battle_free: bool
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        final_bag = dict(self.bag_after)
        return (
            len(self.records) == SAFFRON_CHECKPOINT_COUNT
            and self.money_before >= THUNDER_STONE_PRICE + FRESH_WATER_PRICE
            and self.money_after_stone == self.money_before - THUNDER_STONE_PRICE
            and self.money_after_purchase
            == self.money_after
            == self.money_before - THUNDER_STONE_PRICE - FRESH_WATER_PRICE
            and self.vending_cursor == 0
            and self.fresh_water_before == 0
            and self.fresh_water_after_purchase == 1
            and self.fresh_water_after_guard == 0
            and self.guard_flag_before & GUARD_DRINK_FLAG == 0
            and self.guard_flag_after_consumption & GUARD_DRINK_FLAG == 0
            and self.guard_flag_after_dialogue & GUARD_DRINK_FLAG
            and self.bag_before == self.bag_after
            and int(ItemId.THUNDER_STONE) not in final_bag
            and int(ItemId.FRESH_WATER) not in final_bag
            and int(ItemId.SODA_POP) not in final_bag
            and int(ItemId.LEMONADE) not in final_bag
            and self.final_raw.map_id == MapId.SAFFRON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.battle_state == 0
            and party_core_intact(self.final_raw.party_species_ids)
            and len(self.party_after) == len(self.party_before) + 1
            and self.party_after[:-1] == self.party_before
            and self.party_after[-1] == JOLTEON
            and EEVEE not in self.party_after
            and self.final_raw.first_party_level is not None
            # Preserve the qualified post-Erika lineage, including schedules
            # where the required Gym battles advance the lead to level 44.
            and 42 <= self.final_raw.first_party_level <= 44
            and self.final_raw.first_party_moves == (0x82, 0x46, 0x3A, 0x39)
            and self.final_raw.first_party_pp == (15, 15, 10, 15)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and self.final_raw.first_party_hp == self.party_hp[0]
            and self.final_raw.first_party_max_hp == self.party_max_hp[0]
            and all(status == 0 for status in self.party_status)
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
            "jolteon_recruitment": {
                "gift_species": EEVEE,
                "gift_level": 25,
                "stone_item_id": int(ItemId.THUNDER_STONE),
                "stone_price": THUNDER_STONE_PRICE,
                "money_after_stone": self.money_after_stone,
                "party_before": list(self.party_before),
                "party_after": list(self.party_after),
                "evolved_species": JOLTEON,
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


@dataclass(frozen=True, slots=True)
class SaffronAccessChapterReport:
    """Evidence for the story access itself, without optional party construction."""

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
    party_before: tuple[int, ...]
    party_after: tuple[int, ...]
    lead_level_before: int | None
    lead_moves_before: tuple[int, ...] | None
    lead_pp_before: tuple[int, ...] | None
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    battle_free: bool
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == SAFFRON_ACCESS_CHECKPOINT_COUNT
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
            and self.final_raw.map_id == MapId.SAFFRON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.battle_state == 0
            and self.party_after == self.party_before
            and self.final_raw.first_party_level == self.lead_level_before
            and self.final_raw.first_party_moves == self.lead_moves_before
            and self.final_raw.first_party_pp == self.lead_pp_before
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and self.final_raw.first_party_hp == self.party_hp[0]
            and self.final_raw.first_party_max_hp == self.party_max_hp[0]
            and all(status == 0 for status in self.party_status)
            and self.battle_free
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "reach_saffron",
            "optional_party_construction": False,
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
            "party_preserved": self.party_after == self.party_before,
            "battle_free": self.battle_free,
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


def run_saffron_access_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: SaffronTiming = DEFAULT_SAFFRON_TIMING,
    progress: ProgressSink | None = None,
) -> SaffronAccessChapterReport:
    """Open Saffron from the earliest qualified Celadon boundary.

    Reaching Saffron does not require defeating Erika or recruiting Eevee.  The
    older combined chapter remains available for the canonical balanced-team
    route; this narrower routine proves only the objective it advertises.
    """

    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[SaffronCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.CELADON_POKECENTER, (3, 3), "Celadon access boundary")
    initial_bag = _bag(emulator)
    initial_money = _money(emulator)
    party_before = tuple(initial.party_species_ids or ())
    initial_flag = emulator.read_u8(RamAddress.STATUS_FLAGS_1)
    if (
        not party_before
        or initial_money < FRESH_WATER_PRICE
        or initial_bag.get(ItemId.FRESH_WATER, 0)
        or initial_bag.get(ItemId.SODA_POP, 0)
        or initial_bag.get(ItemId.LEMONADE, 0)
        or initial_flag & GUARD_DRINK_FLAG
        or _party_hp(emulator) != _party_max_hp(emulator)
        or any(_party_status(emulator))
    ):
        raise SaffronChapterError("Saffron access input boundary is not pristine.")
    _checkpoint(
        records, progress, emulator, initial, "saffron_access_ready", "Celadon boundary ready"
    )

    _move(actions, reader, emulator, CENTER_EXIT, timing, "Celadon Center exit")
    _require(reader.read(), MapId.CELADON_CITY, (41, 10), "Celadon Center exterior")
    outward_legs = (
        (CITY_TO_MART, MapId.CELADON_MART_1F, (16, 7), "mart_1f"),
        (MART_1F_TO_2F, MapId.CELADON_MART_2F, (12, 2), "mart_2f"),
        (MART_2F_TO_3F, MapId.CELADON_MART_3F, (16, 2), "mart_3f"),
        (MART_3F_TO_4F, MapId.CELADON_MART_4F, (12, 2), "mart_4f"),
        (MART_4F_TO_5F, MapId.CELADON_MART_5F, (16, 2), "mart_5f"),
        (MART_5F_TO_ROOF, MapId.CELADON_MART_ROOF, (15, 3), "mart_roof"),
    )
    for route, map_id, coordinate, label in outward_legs:
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
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    _select_cursor(actions, emulator, 0, DEFAULT_LAVENDER_TIMING)
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
    _move(actions, reader, emulator, ("right",), timing, "guard trigger", allow_script=True)
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
        final_flag = emulator.read_u8(RamAddress.STATUS_FLAGS_1)
        if final_flag & GUARD_DRINK_FLAG and reader.read_input_readiness().ready:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=1)
    else:
        raise SaffronChapterError("Guard dialogue did not grant global Saffron access.")
    _checkpoint(
        records, progress, emulator, reader.read(), "guards_bribed", "Global guard access set"
    )

    _move(actions, reader, emulator, GATE_TO_SAFFRON, timing, "Saffron crossing")
    _require(reader.read(), MapId.SAFFRON_CITY, (1, 18), "Saffron entry")
    _checkpoint(
        records, progress, emulator, reader.read(), "saffron_entered", "Entered Saffron City"
    )
    _move(actions, reader, emulator, SAFFRON_TO_CENTER, timing, "Saffron Center")
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "Saffron Center entry")
    _move(actions, reader, emulator, ("up",) * 4, timing, "Saffron nurse")
    for _ in range(9):
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    for _ in range(timing.heal_pulses):
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and all(status == 0 for status in _party_status(emulator))
            and reader.read_input_readiness().ready
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=1)
    else:
        raise SaffronChapterError("Saffron Center healing did not settle.")
    final = reader.read()
    _checkpoint(records, progress, emulator, final, "saffron_stable", "Healed Saffron boundary")

    report = SaffronAccessChapterReport(
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
        party_before=party_before,
        party_after=tuple(final.party_species_ids or ()),
        lead_level_before=initial.first_party_level,
        lead_moves_before=initial.first_party_moves,
        lead_pp_before=initial.first_party_pp,
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        battle_free=final.battle_state == 0,
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise SaffronChapterError(
            f"Saffron access evidence contract failed: {report.public_dict()!r}."
        )
    return report


def run_saffron_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: SaffronTiming = DEFAULT_SAFFRON_TIMING,
    progress: ProgressSink | None = None,
) -> SaffronChapterReport:
    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[SaffronCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.CELADON_POKECENTER, (3, 3), "Erika boundary")
    initial_bag = _bag(emulator)
    initial_money = _money(emulator)
    party_before = tuple(initial.party_species_ids or ())
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

    _move(actions, reader, emulator, CENTER_EXIT, timing, "Celadon Center exit")
    _require(reader.read(), MapId.CELADON_CITY, (41, 10), "Celadon Center exterior")
    _move(
        actions,
        reader,
        emulator,
        CITY_TO_MANSION_REAR,
        timing,
        "Celadon Mansion rear entrance",
    )
    if reader.read().map_id == MapId.CELADON_CITY and (
        reader.read().player_x,
        reader.read().player_y,
    ) == (25, 3):
        _move(
            actions,
            reader,
            emulator,
            ("down", "left"),
            timing,
            "Celadon Mansion left rear door",
        )
    if reader.read().map_id == MapId.CELADON_CITY:
        actions.execute(MacroAction(MacroActionKind.INTERACT))
        _wait(actions, timing.movement_frames)
    _require(reader.read(), MapId.CELADON_MANSION_1F, (3, 1), "Mansion rear entrance")
    mansion_legs = (
        (
            MANSION_1F_REAR_STAIRS,
            MapId.CELADON_MANSION_2F,
            (2, 1),
            "Mansion rear second floor",
        ),
        (
            MANSION_2F_REAR_STAIRS,
            MapId.CELADON_MANSION_3F,
            (4, 1),
            "Mansion rear third floor",
        ),
        (
            MANSION_3F_REAR_STAIRS,
            MapId.CELADON_MANSION_ROOF,
            (2, 2),
            "Mansion rear roof",
        ),
        (
            MANSION_ROOF_TO_HOUSE,
            MapId.CELADON_MANSION_ROOF_HOUSE,
            (2, 7),
            "Mansion roof house",
        ),
        (
            ROOF_HOUSE_TO_EEVEE,
            MapId.CELADON_MANSION_ROOF_HOUSE,
            (4, 2),
            "Eevee gift stance",
        ),
    )
    for route, map_id, coordinate, label in mansion_legs:
        _move(actions, reader, emulator, route, timing, label)
        _require(reader.read(), map_id, coordinate, label)
    _receive_eevee(actions, reader, emulator, party_before, timing)
    _checkpoint(records, progress, emulator, reader.read(), "eevee_received", "Received Eevee")

    exit_legs = (
        (
            EEVEE_TO_ROOF_HOUSE_EXIT,
            MapId.CELADON_MANSION_ROOF,
            (2, 8),
            "Eevee room exit",
        ),
        (
            MANSION_ROOF_TO_3F,
            MapId.CELADON_MANSION_3F,
            (2, 1),
            "Mansion roof descent",
        ),
        (
            MANSION_3F_TO_2F,
            MapId.CELADON_MANSION_2F,
            (4, 1),
            "Mansion third-floor descent",
        ),
        (
            MANSION_2F_TO_1F,
            MapId.CELADON_MANSION_1F,
            (2, 1),
            "Mansion second-floor descent",
        ),
        (
            MANSION_1F_TO_CITY,
            MapId.CELADON_CITY,
            (25, 3),
            "Mansion rear exit",
        ),
    )
    for route, map_id, coordinate, label in exit_legs:
        _move(actions, reader, emulator, route, timing, label)
        _require(reader.read(), map_id, coordinate, label)
    mansion_exit = reader.read()
    rear_to_center = (
        MANSION_REAR_TO_CENTER_EXTERIOR_24
        if (mansion_exit.player_x, mansion_exit.player_y) == (24, 3)
        else MANSION_REAR_TO_CENTER_EXTERIOR_25
    )
    _move(
        actions,
        reader,
        emulator,
        rear_to_center,
        timing,
        "Mansion rear to Celadon Center exterior",
    )
    _require(reader.read(), MapId.CELADON_CITY, (41, 10), "Celadon Center exterior return")

    money_after_stone: int | None = None
    legs = (
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
        if map_id == MapId.CELADON_MART_4F:
            money_after_stone = _purchase_thunder_stone(actions, reader, emulator, timing)
            _evolve_eevee(actions, reader, emulator, timing)
            _checkpoint(
                records,
                progress,
                emulator,
                reader.read(),
                "jolteon_evolved",
                "Evolved Eevee into Jolteon",
            )
    _checkpoint(records, progress, emulator, reader.read(), "roof_reached", "Reached vending roof")

    _move(actions, reader, emulator, ROOF_TO_VENDING, timing, "vending stance")
    _require(reader.read(), MapId.CELADON_MART_ROOF, (12, 3), "vending stance")
    # The machine is directly above the stance tile.  A downward input walks
    # away from it and can silently invalidate the purchase sequence.
    actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
    _wait(actions, timing.movement_frames)
    _require(reader.read(), MapId.CELADON_MART_ROOF, (12, 3), "vending facing")
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(actions, timing.movement_frames)
    # The first prompt is vending-machine dialogue, not the drink list.  The
    # cursor address still contains the earlier stone-shop selection until this
    # prompt is acknowledged.
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    _select_cursor(actions, emulator, 0, DEFAULT_LAVENDER_TIMING)
    vending_cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
    if vending_cursor != 0:
        raise SaffronChapterError(f"Fresh Water was not vending cursor zero: {vending_cursor}.")
    for _ in range(timing.vending_pulses):
        if (
            _money(emulator) == money_after_stone - FRESH_WATER_PRICE
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
            and all(status == 0 for status in _party_status(emulator))
            and raw.first_party_pp == (15, 15, 10, 15)
            and reader.read_input_readiness().ready
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=1)
    else:
        raise SaffronChapterError("Saffron Center healing did not settle.")
    final = reader.read()
    _checkpoint(records, progress, emulator, final, "saffron_stable", "Healed Saffron boundary")

    if money_after_stone is None:
        raise SaffronChapterError("Thunder Stone purchase was not observed.")

    report = SaffronChapterReport(
        records=tuple(records),
        final_raw=final,
        money_before=initial_money,
        money_after_stone=money_after_stone,
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
        party_before=party_before,
        party_after=tuple(final.party_species_ids or ()),
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


def _receive_eevee(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    party_before: tuple[int, ...],
    timing: SaffronTiming,
) -> None:
    expected = (*party_before, EEVEE)
    stances = (
        (Coordinate(4, 2), "down"),
        (Coordinate(5, 3), "left"),
        (Coordinate(4, 5), "up"),
    )
    for stance, facing in stances:
        raw = reader.read()
        current = Coordinate(raw.player_x or 0, raw.player_y or 0)
        route = path_to_directions(shortest_path(ROOF_HOUSE_GRID, current, stance))
        _move(
            actions,
            reader,
            emulator,
            tuple(str(direction) for direction in route),
            timing,
            f"Eevee interaction stance {stance.x},{stance.y}",
        )
        actions.execute(MacroAction(MacroActionKind.MOVE, facing))
        _wait(actions, timing.movement_frames)
        actions.execute(MacroAction(MacroActionKind.INTERACT))
        _wait(actions, timing.movement_frames)
        for _ in range(16):
            party = tuple(reader.read().party_species_ids or ())
            if party == expected and reader.read_input_readiness().ready:
                _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
                return
            action = (
                MacroActionKind.CANCEL if len(party) == len(expected) else MacroActionKind.CONFIRM
            )
            _pulse(actions, action, frames=timing.movement_frames)
        for _ in range(4):
            _pulse(actions, MacroActionKind.CANCEL, frames=timing.movement_frames)
    raw = reader.read()
    raise SaffronChapterError(
        f"Celadon Mansion Eevee gift did not settle: party="
        f"{tuple(raw.party_species_ids or ())!r}, "
        f"position={(raw.map_id, raw.player_x, raw.player_y)!r}."
    )


def _purchase_thunder_stone(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SaffronTiming,
) -> int:
    before_money = _money(emulator)
    if _bag(emulator).get(ItemId.THUNDER_STONE, 0):
        raise SaffronChapterError("Thunder Stone unexpectedly existed before purchase.")
    _move(
        actions,
        reader,
        emulator,
        MART_4F_TO_STONE_CLERK,
        timing,
        "evolution-stone clerk",
    )
    # The clerk is behind a two-tile counter. Gen I lets the player interact
    # across it from (5, 5); (5, 6) is a counter tile, not a walkable stance.
    _require(reader.read(), MapId.CELADON_MART_4F, (5, 5), "evolution-stone clerk")
    actions.execute(MacroAction(MacroActionKind.MOVE, "down"))
    _wait(actions, timing.movement_frames)
    _open_mart_buy_list(actions, emulator, DEFAULT_LAVENDER_TIMING.wait_frames)
    try:
        _buy_mart_item(
            actions,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            absolute_index=2,
            item=ItemId.THUNDER_STONE,
            quantity=1,
            target_bag_quantity=1,
        )
        _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    except LavenderChapterError as error:
        raise SaffronChapterError(f"Thunder Stone purchase failed: {error}") from error
    after_money = _money(emulator)
    if (
        _bag(emulator).get(ItemId.THUNDER_STONE, 0) != 1
        or before_money - after_money != THUNDER_STONE_PRICE
    ):
        raise SaffronChapterError("Thunder Stone economy proof failed.")
    _move(
        actions,
        reader,
        emulator,
        STONE_CLERK_TO_MART_4F_STAIRS,
        timing,
        "fourth-floor stair return",
    )
    _require(reader.read(), MapId.CELADON_MART_4F, (12, 2), "fourth-floor stair return")
    return after_money


def _open_mart_buy_list(
    actions: CountingExecutor,
    emulator: EmulatorState,
    wait_frames: int,
) -> None:
    """Advance clerk dialogue until the priced item list is actually active."""

    for _ in range(8):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (5, 4):
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=wait_frames)
    raise SaffronChapterError("Mart dialogue did not reach the priced item list.")


def _evolve_eevee(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SaffronTiming,
) -> None:
    before = tuple(reader.read().party_species_ids or ())
    if not before or before[-1] != EEVEE:
        raise SaffronChapterError(f"Evolution target is not Eevee: {before!r}.")
    try:
        _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
        _select_bag_item(actions, emulator, ItemId.THUNDER_STONE, DEFAULT_LAVENDER_TIMING)
        _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_LAVENDER_TIMING.wait_frames)
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        _select_cursor(actions, emulator, len(before) - 1, DEFAULT_LAVENDER_TIMING)
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        for _ in range(64):
            party = tuple(reader.read().party_species_ids or ())
            if (
                party == (*before[:-1], JOLTEON)
                and _bag(emulator).get(ItemId.THUNDER_STONE, 0) == 0
            ):
                _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
                return
            _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    except LavenderChapterError as error:
        raise SaffronChapterError(f"Eevee evolution menu failed: {error}") from error
    raise SaffronChapterError(
        f"Thunder Stone did not evolve Eevee: {tuple(reader.read().party_species_ids or ())!r}."
    )


def _move(
    actions: CountingExecutor,
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
            if (
                label == "evolution-stone clerk"
                and before.map_id == MapId.CELADON_MART_4F
                and (before.player_x, before.player_y) in STONE_CLERK_WALKER_BLOCK_POSITIONS
                and direction == "left"
            ):
                after = _yield_to_stone_clerk_walker(
                    actions,
                    reader,
                    timing,
                    block_position=(before.player_x or 0, before.player_y or 0),
                )
                break
            if (
                label == "fourth-floor stair return"
                and before.map_id == MapId.CELADON_MART_4F
                and before.player_y == STONE_CLERK_RETURN_BLOCK_POSITION[1]
                and STONE_CLERK_RETURN_RETREAT_POSITION[0]
                <= (before.player_x or -1)
                <= STONE_CLERK_RETURN_MAX_X
                and direction == "right"
            ):
                after = _yield_from_stone_clerk_return(
                    actions,
                    reader,
                    emulator,
                    timing,
                    target_x=(before.player_x or 0) + 1,
                )
                break
            if (
                label == "mart_roof"
                and before.map_id == MapId.CELADON_MART_5F
                and (before.player_x, before.player_y) == MART_5F_GENTLEMAN_BLOCK_POSITION
                and direction == "left"
            ):
                after = _yield_to_mart_5f_gentleman(actions, reader, timing)
                break
            if (
                label == "mart_1f_return"
                and before.map_id == MapId.CELADON_MART_2F
                and (before.player_x, before.player_y) == MART_2F_RETURN_BLOCK_POSITION
                and direction == "left"
            ):
                after = _cross_mart_2f_return_customer(
                    actions,
                    reader,
                    emulator,
                    timing,
                )
                break
        else:
            raise SaffronChapterError(
                f"{label} blocked at step {index}: {direction}; "
                f"{(after.map_id, after.player_x, after.player_y)!r}."
            )


def _yield_to_mart_5f_gentleman(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SaffronTiming,
) -> RawGameState:
    """Yield the top aisle until the fifth-floor customer can pass."""

    for attempt in range(MART_5F_GENTLEMAN_CLEAR_ATTEMPTS):
        state = reader.read()
        if (state.player_x, state.player_y) == MART_5F_GENTLEMAN_CLEAR_POSITION:
            return state
        if (
            state.map_id != MapId.CELADON_MART_5F
            or state.battle_state != 0
            or (state.player_x, state.player_y) != MART_5F_GENTLEMAN_BLOCK_POSITION
        ):
            raise SaffronChapterError("Celadon Mart 5F recovery left its bounded top-aisle gate.")
        actions.execute(MacroAction(MacroActionKind.MOVE, "down"))
        _wait(actions, timing.movement_frames)
        yielded = reader.read()
        if (yielded.player_x, yielded.player_y) != MART_5F_GENTLEMAN_YIELD_POSITION:
            raise SaffronChapterError("Celadon Mart 5F could not yield the top aisle.")
        for return_attempt in range(MART_5F_GENTLEMAN_CLEAR_ATTEMPTS):
            _wait(actions, timing.movement_frames * (attempt + return_attempt + 1))
            actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
            _wait(actions, timing.movement_frames)
            returned = reader.read()
            if (returned.player_x, returned.player_y) == MART_5F_GENTLEMAN_BLOCK_POSITION:
                break
            if (returned.player_x, returned.player_y) != MART_5F_GENTLEMAN_YIELD_POSITION:
                raise SaffronChapterError("Celadon Mart 5F recovery left its bounded yield tile.")
        else:
            raise SaffronChapterError("Celadon Mart 5F did not release the return tile.")
        actions.execute(MacroAction(MacroActionKind.MOVE, "left"))
        _wait(actions, timing.movement_frames)
        crossed = reader.read()
        if (crossed.player_x, crossed.player_y) == MART_5F_GENTLEMAN_CLEAR_POSITION:
            return crossed
        if (crossed.player_x, crossed.player_y) != MART_5F_GENTLEMAN_BLOCK_POSITION:
            raise SaffronChapterError("Celadon Mart 5F recovery left its bounded crossing gate.")
    raise SaffronChapterError("Celadon Mart 5F customer did not clear the top aisle.")


def _yield_to_stone_clerk_walker(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SaffronTiming,
    *,
    block_position: tuple[int, int],
) -> RawGameState:
    """Yield east until the fourth-floor customer vacates the clerk route."""

    if block_position not in STONE_CLERK_WALKER_BLOCK_POSITIONS:
        raise ValueError("stone-clerk walker block position must be a declared corridor gate")
    clear_position = (block_position[0] - 1, block_position[1])
    yield_position = (block_position[0] + 1, block_position[1])

    for attempt in range(STONE_CLERK_WALKER_CLEAR_ATTEMPTS):
        state = reader.read()
        if (state.player_x, state.player_y) == clear_position:
            return state
        if (
            state.map_id != MapId.CELADON_MART_4F
            or state.battle_state != 0
            or (state.player_x, state.player_y) != block_position
        ):
            raise SaffronChapterError(
                "Evolution-stone walker recovery left its bounded corridor gate."
            )
        actions.execute(MacroAction(MacroActionKind.MOVE, "right"))
        _wait(actions, timing.movement_frames)
        yielded = reader.read()
        if (yielded.player_x, yielded.player_y) != yield_position:
            raise SaffronChapterError(
                "Evolution-stone walker recovery could not yield the corridor."
            )
        _wait(actions, timing.movement_frames * (attempt + 1))
        for return_attempt in range(STONE_CLERK_WALKER_CLEAR_ATTEMPTS):
            actions.execute(MacroAction(MacroActionKind.MOVE, "left"))
            _wait(actions, timing.movement_frames)
            returned = reader.read()
            if (returned.player_x, returned.player_y) == block_position:
                break
            if (returned.player_x, returned.player_y) != yield_position:
                raise SaffronChapterError(
                    "Evolution-stone walker recovery left its bounded yield gate."
                )
            _wait(actions, timing.movement_frames * (return_attempt + 1))
        else:
            raise SaffronChapterError(
                "Evolution-stone walker recovery could not restore its approach gate."
            )
        actions.execute(MacroAction(MacroActionKind.MOVE, "left"))
        _wait(actions, timing.movement_frames)
        state = reader.read()
        if (state.player_x, state.player_y) == clear_position:
            return state
    raise SaffronChapterError("Evolution-stone walker did not clear within its bounded retries.")


def _cross_mart_2f_return_customer(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SaffronTiming,
) -> RawGameState:
    """Observe the moving 2F customer and cross the top aisle when it clears."""

    for _ in range(MART_2F_RETURN_CLEAR_FRAMES):
        state = reader.read()
        if (state.player_x, state.player_y) == MART_2F_RETURN_CLEAR_POSITION:
            return state
        if (
            state.map_id != MapId.CELADON_MART_2F
            or state.battle_state != 0
            or (state.player_x, state.player_y) != MART_2F_RETURN_BLOCK_POSITION
        ):
            raise SaffronChapterError(
                "Celadon Mart 2F customer recovery left its bounded aisle gate."
            )
        customer = (
            emulator.read_u8(MART_2F_GIRL_X) - 4,
            emulator.read_u8(MART_2F_GIRL_Y) - 4,
        )
        if customer != MART_2F_RETURN_CLEAR_POSITION:
            actions.execute(MacroAction(MacroActionKind.MOVE, "left"))
            _wait(actions, timing.movement_frames)
            crossed = reader.read()
            if (crossed.player_x, crossed.player_y) == MART_2F_RETURN_CLEAR_POSITION:
                return crossed
            if (crossed.player_x, crossed.player_y) != MART_2F_RETURN_BLOCK_POSITION:
                raise SaffronChapterError(
                    "Celadon Mart 2F customer recovery observed an invalid displacement."
                )
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=1))
    raise SaffronChapterError("Celadon Mart 2F customer did not clear the top aisle.")


def _yield_from_stone_clerk_return(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SaffronTiming,
    *,
    target_x: int,
) -> RawGameState:
    """Retreat west so the fourth-floor customer can cross the return corridor."""

    if not 2 <= target_x <= STONE_CLERK_RETURN_MAX_X + 1:
        raise ValueError("stone-clerk return target must stay inside the fourth-floor corridor")

    for _ in range(STONE_CLERK_WALKER_CLEAR_ATTEMPTS):
        state = reader.read()
        if (
            state.map_id != MapId.CELADON_MART_4F
            or state.battle_state != 0
            or state.player_y != STONE_CLERK_RETURN_BLOCK_POSITION[1]
            or not (STONE_CLERK_RETURN_RETREAT_POSITION[0] <= (state.player_x or -1) < target_x)
        ):
            raise SaffronChapterError(
                "Evolution-stone return recovery left its bounded corridor gate."
            )
        while (state.player_x, state.player_y) != STONE_CLERK_RETURN_RETREAT_POSITION:
            before_x = state.player_x
            actions.execute(MacroAction(MacroActionKind.MOVE, "left"))
            _wait(actions, timing.movement_frames)
            state = reader.read()
            if state.map_id != MapId.CELADON_MART_4F or state.player_y != 2:
                raise SaffronChapterError(
                    "Evolution-stone return recovery left the fourth-floor corridor."
                )
            if state.player_x != (before_x or 0) - 1:
                raise SaffronChapterError(
                    "Evolution-stone return recovery could not reach its retreat gate."
                )
        actions.execute(MacroAction(MacroActionKind.MOVE, "down"))
        _wait(actions, timing.movement_frames)
        state = reader.read()
        if (state.player_x, state.player_y) != STONE_CLERK_RETURN_YIELD_POSITION:
            raise SaffronChapterError(
                "Evolution-stone return recovery could not enter its yield alcove."
            )
        # Test the actual collision boundary instead of inferring availability
        # from one NPC coordinate.  A held-out timing lineage left the walker
        # on another row, where the old row-specific predicate waited forever
        # even though the entrance itself could be retried safely.
        for _ in range(STONE_CLERK_RETURN_CLEAR_FRAMES):
            actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
            _wait(actions, timing.movement_frames)
            state = reader.read()
            if (state.player_x, state.player_y) == STONE_CLERK_RETURN_RETREAT_POSITION:
                break
            if (state.player_x, state.player_y) != STONE_CLERK_RETURN_YIELD_POSITION:
                raise SaffronChapterError("Evolution-stone return recovery left its yield alcove.")
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=1))
        else:
            raise SaffronChapterError(
                "Evolution-stone return recovery could not reenter the corridor."
            )
        while state.player_x != target_x:
            before_x = state.player_x
            actions.execute(MacroAction(MacroActionKind.MOVE, "right"))
            _wait(actions, timing.movement_frames)
            advanced = reader.read()
            if advanced.map_id != MapId.CELADON_MART_4F or advanced.player_y != 2:
                raise SaffronChapterError(
                    "Evolution-stone return recovery left the fourth-floor corridor."
                )
            if advanced.player_x == (before_x or 0) + 1:
                state = advanced
                continue
            if advanced.player_x != before_x:
                raise SaffronChapterError(
                    "Evolution-stone return recovery observed an invalid displacement."
                )
            state = advanced
            break
        if state.player_x == target_x and state.player_y == 2:
            return state
    raise SaffronChapterError("Evolution-stone walker did not clear the stair-return corridor.")


def _pulse(
    actions: CountingExecutor,
    kind: MacroActionKind,
    *,
    frames: int,
) -> None:
    actions.execute(MacroAction(kind))
    _wait(actions, frames)


def _wait(actions: CountingExecutor, frames: int) -> None:
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _require(raw: RawGameState, map_id: MapId, coordinate: tuple[int, int], label: str) -> None:
    if raw.map_id != map_id or (raw.player_x, raw.player_y) != coordinate or raw.battle_state != 0:
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
