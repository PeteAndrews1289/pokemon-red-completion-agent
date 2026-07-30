"""Qualified Silph Co. liberation chapter.

The routes, required trainers, scripted battles, and event IDs are pinned to
pret/pokered commit ``1e96034092686d006e863cace09e87273051a3d8``.
"""

from __future__ import annotations

from collections import deque
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
from pokemon_red_completion.celadon import (
    _bag,
    _money,
    _party_hp,
    _party_max_hp,
    _party_status,
)
from pokemon_red_completion.lavender import (
    LavenderTiming,
    _buy_mart_item,
    _clear_field_text,
    _close_menus,
    _open_bag,
    _select_bag_item,
    _select_cursor,
    _use_bag_item,
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
from pokemon_red_completion.saffron import (
    CITY_TO_ROUTE_7,
    FRESH_WATER_PRICE,
    GATE_TO_SAFFRON,
    MART_1F_TO_2F,
    MART_2F_TO_1F,
    MART_2F_TO_3F,
    MART_3F_TO_2F,
    MART_3F_TO_4F,
    MART_4F_TO_3F,
    MART_4F_TO_5F,
    MART_5F_TO_4F,
    MART_5F_TO_ROOF,
    MART_TO_CITY,
    ROOF_TO_5F,
    ROOF_TO_VENDING,
    ROUTE_7_TO_GATE,
    SAFFRON_TO_CENTER,
)
from pokemon_red_completion.tower import TOWER_FINAL_PARTY

SILPH_CHECKPOINT_COUNT = 12
HYPER_POTION_PURCHASE_QUANTITY = 6
HYPER_POTION_PRICE = 1_500
STATUS_FLAGS_4 = 0xD72E
GOT_LAPRAS_MASK = 0x01
ICE_BEAM_MOVE = 0x3A
ROOF_GIRL_Y = 0xC224
ROOF_GIRL_X = 0xC225
ROOF_NERD_Y = 0xC214
ROOF_NERD_X = 0xC215
ROOF_WALKABLE = frozenset(
    (x, y)
    for y, row in enumerate(
        (
            "####################",
            "##........##########",
            "##..##......###.####",
            "##..##............##",
            "##......##........##",
            "##......##........##",
            "##................##",
            "####################",
        )
    )
    for x, tile in enumerate(row)
    if tile == "."
)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[c] for c in value)


def _reverse(route: Iterable[str]) -> tuple[str, ...]:
    opposite = {"up": "down", "down": "up", "left": "right", "right": "left"}
    return tuple(opposite[direction] for direction in reversed(tuple(route)))


CENTER_EXIT = _directions("DDDDD")
CITY_TO_MART_APPROACH = _directions("RRRRRDRRRRRRRRRRRRURRRRRRRRRRUUUUUUUUUUUUUUUUUULLLLLLLLLLL")
MART_DOOR = ("up",)
MART_TO_CLERK = _directions("ULU")
CLERK_TO_EXIT = _directions("RDD")
MART_TO_SILPH = _directions("DRRRRRRRRRRRDDDDDDDDDDDLLLLLLLLLLLLLLLLLLU")
CENTER_TO_SILPH = _directions("LLLLLLUUUUUUUURRRRRRRRRRRRRRRU")
SILPH_DOOR = ("up",)
SILPH_1F_TO_ELEVATOR = _directions("UUUUUUUULULUUUUUUURRRRRRRRRRRRU")
ELEVATOR_TO_PANEL = _directions("UURR")
ELEVATOR_EXIT = _directions("LLDDD")
FIFTH_FLOOR_TO_WARP = _directions("DDLLLLLLDLLLLDLDDDDDDDDD")
CARD_KEY_APPROACH = ("right",) * 11
CARD_KEY_RETURN = ("left",) * 11
FIFTH_FLOOR_TO_ELEVATOR = _directions("UUUUUUUUUURRRRUUURRRRRRR")
THIRD_FLOOR_GUARD = _directions("DDDDDLLD")
THIRD_FLOOR_TO_7F = _directions("DLLDLLLLL")
SEVENT_TO_THIRD = _directions("URRRUURRRRUUUUUUURR")
THIRD_TO_SEVENT = _directions("LLDDDDDDDLLLLDDLLLD")
SILPH_1F_TO_EXIT = _directions("DLLLLLLLLLDLDLDLDDDRDRDDDDDDDD")
CITY_TO_CENTER = _directions("DLLLLLLLLLLLLLLLDDDDDDDDRRRRRRUUUUU")
SEVENT_TO_11F = _directions("ULLDDDDRRD")
ROCKET_TO_11F_DOOR = _directions("LDDDDRRRRRRUU")
GIOVANNI_TO_PRESIDENT = _directions("LLUUUUUUUR")
PRESIDENT_TO_11F_WARP = _directions("LDDDDRDDDDDLLLUUUUUUUUUUULUUR")
SEVENT_TO_THIRD_WARP = _directions("ULLUUUURRD")
SAFFRON_CENTER_TO_ROUTE_7_GATE = (
    CENTER_EXIT + _reverse(SAFFRON_TO_CENTER[:-1]) + _reverse(GATE_TO_SAFFRON)
)
ROUTE_7_GATE_TO_WEST = ("left",) * 4
# The forward route jumps a southbound ledge at (9, 3)->(9, 4), so it is not
# reversible. This source-derived path crosses the lower opening at y=8 and
# returns north through the x=4 corridor instead.
ROUTE_7_WEST_TO_CONNECTION = _directions("LLLUULLLLUUUUUULLLLD")
ROUTE_7_CONNECTION_TO_CELADON_CITY = _reverse(CITY_TO_ROUTE_7)
CELADON_CITY_TO_MART = ("up",)
ROOF_TO_SAFFRON_CENTER = (
    ROOF_TO_5F
    + MART_5F_TO_4F
    + MART_4F_TO_3F
    + MART_3F_TO_2F
    + MART_2F_TO_1F
    + MART_TO_CITY
    + CITY_TO_ROUTE_7
    + ROUTE_7_TO_GATE
    + GATE_TO_SAFFRON
    + SAFFRON_TO_CENTER
)


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class SilphChapterError(RuntimeError):
    """Raised when the Silph evidence contract fails."""


@dataclass(frozen=True, slots=True)
class SilphTiming:
    movement_frames: int = 720
    menu_frames: int = 240
    battle_item_menu_frames: int = 120
    battle_item_frames: int = 180
    dialogue_frames: int = 1_200
    script_frames: int = 2_400
    max_script_pulses: int = 24
    heal_pulses: int = 9

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_SILPH_TIMING = SilphTiming()


@dataclass(frozen=True, slots=True)
class SilphProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[SilphProgress], None]


@dataclass(frozen=True, slots=True)
class SilphCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class SilphChapterReport:
    records: tuple[SilphCheckpoint, ...]
    final_raw: RawGameState
    money_before: int
    money_after: int
    tm13_event: bool
    tm13_transfer_before_event: bool
    other_roof_rewards_untouched: bool
    fresh_water_after_reward: int
    tm13_after_teaching: int
    upgraded_moves: tuple[int, int, int, int]
    upgraded_pp: tuple[int, int, int, int]
    rival_potions_used: int
    hyper_potions_remaining: int
    max_repel_remaining: int
    card_key_quantity: int
    master_ball_quantity: int
    required_events: tuple[tuple[int, bool], ...]
    lapras_flag_before: int
    lapras_flag_after: int
    party_hp: tuple[int, int, int]
    party_max_hp: tuple[int, int, int]
    party_status: tuple[int, int, int]
    controller_released: bool
    frames_executed: int
    actions_executed: int

    @property
    def passed(self) -> bool:
        events = dict(self.required_events)
        return (
            len(self.records) == SILPH_CHECKPOINT_COUNT
            and all(events.values())
            and self.tm13_event
            and self.tm13_transfer_before_event
            and self.other_roof_rewards_untouched
            and self.fresh_water_after_reward == 0
            and self.tm13_after_teaching == 0
            and self.upgraded_moves == (0x82, 0x46, ICE_BEAM_MOVE, 0x39)
            and self.upgraded_pp == (15, 15, 10, 15)
            and self.money_before == 41_345
            and self.money_after == 40_894
            and 0 <= self.rival_potions_used <= 1
            and self.hyper_potions_remaining
            == HYPER_POTION_PURCHASE_QUANTITY - self.rival_potions_used
            and self.max_repel_remaining == 0
            and self.card_key_quantity == 1
            and self.master_ball_quantity == 1
            and self.lapras_flag_before & GOT_LAPRAS_MASK == 0
            and self.lapras_flag_after & GOT_LAPRAS_MASK == 0
            and self.final_raw.map_id == MapId.SAFFRON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.battle_state == 0
            and self.final_raw.party_species_ids == TOWER_FINAL_PARTY
            and self.final_raw.first_party_moves == (0x82, 0x46, ICE_BEAM_MOVE, 0x39)
            and self.final_raw.first_party_pp == (15, 15, 10, 15)
            and self.party_hp == self.party_max_hp
            and self.party_status == (0, 0, 0)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "liberate_silph",
            "ice_beam_upgrade": {
                "tm13_event": self.tm13_event,
                "item_transfer_before_event": self.tm13_transfer_before_event,
                "other_roof_rewards_untouched": self.other_roof_rewards_untouched,
                "fresh_water_remaining": self.fresh_water_after_reward,
                "tm13_remaining": self.tm13_after_teaching,
                "moves": list(self.upgraded_moves),
                "pp": list(self.upgraded_pp),
            },
            "supply": {
                "hyper_potions_bought": HYPER_POTION_PURCHASE_QUANTITY,
                "used_by_rival_policy": self.rival_potions_used,
                "remaining": self.hyper_potions_remaining,
                "max_repel_bought": 1,
                "max_repel_remaining": self.max_repel_remaining,
            },
            "required_events": {f"{event:#05x}": value for event, value in self.required_events},
            "key_items": {
                "card_key": self.card_key_quantity,
                "master_ball": self.master_ball_quantity,
            },
            "optional_lapras_untouched": not bool(self.lapras_flag_after & GOT_LAPRAS_MASK),
            "money": [self.money_before, self.money_after],
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


def run_silph_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: SilphTiming = DEFAULT_SILPH_TIMING,
    progress: ProgressSink | None = None,
) -> SilphChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[SilphCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.SAFFRON_POKECENTER, (3, 3), "Saffron boundary")
    money_before = _money(emulator)
    lapras_before = emulator.read_u8(STATUS_FLAGS_4)
    initial_bag = _bag(emulator)
    if (
        initial_bag.get(ItemId.CARD_KEY, 0)
        or initial_bag.get(ItemId.MASTER_BALL, 0)
        or initial_bag.get(ItemId.HYPER_POTION, 0)
        or initial_bag.get(ItemId.FRESH_WATER, 0)
        or initial_bag.get(ItemId.TM13_ICE_BEAM, 0)
        or _event(emulator, EventFlag.GOT_TM13)
        or _event(emulator, 0x18D)
        or _event(emulator, 0x18E)
        or lapras_before & GOT_LAPRAS_MASK
    ):
        raise SilphChapterError("Silph input boundary is not pristine.")
    _checkpoint(records, progress, emulator, initial, "silph_ready", "Silph plan ready")

    _move(actions, reader, CENTER_EXIT, timing)
    _move(actions, reader, CITY_TO_MART_APPROACH, timing)
    _move(actions, reader, MART_DOOR, timing)
    _require(reader.read(), MapId.SAFFRON_MART, (3, 7), "Saffron Mart")
    _move(actions, reader, MART_TO_CLERK, timing)
    _buy_supplies(actions, reader, emulator, timing)
    if (
        _bag(emulator).get(ItemId.HYPER_POTION, 0) != HYPER_POTION_PURCHASE_QUANTITY
        or _bag(emulator).get(ItemId.MAX_REPEL, 0) != 1
    ):
        raise SilphChapterError("Silph supply purchase failed.")
    _require(reader.read(), MapId.SAFFRON_MART, (2, 5), "Saffron clerk return")
    _move(actions, reader, CLERK_TO_EXIT, timing)
    _move(actions, reader, ("down",), timing)
    _move(actions, reader, _reverse(CITY_TO_MART_APPROACH), timing)
    _move(actions, reader, ("up",), timing)
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "Saffron supply return")
    _move(actions, reader, ("up",) * 4, timing)
    _use_bag_item(  # type: ignore[arg-type]
        actions,
        reader,
        emulator,
        LavenderTiming(wait_frames=timing.menu_frames),
        ItemId.MAX_REPEL,
    )

    upgraded, tm13_transfer_ordered = _acquire_and_teach_ice_beam(actions, reader, emulator, timing)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "silph_supplied",
        "Bought supplies and taught Ice Beam",
    )

    _move(actions, reader, CENTER_EXIT, timing)
    _move(actions, reader, CENTER_TO_SILPH, timing)
    _require(reader.read(), MapId.SILPH_CO_1F, (10, 17), "Silph 1F")
    _move(actions, reader, SILPH_1F_TO_ELEVATOR, timing)
    _select_elevator_floor(actions, reader, emulator, 4, timing)
    _move(actions, reader, ELEVATOR_EXIT, timing)
    _require(reader.read(), MapId.SILPH_CO_5F, (20, 1), "Silph 5F")

    _move(actions, reader, FIFTH_FLOOR_TO_WARP, timing)
    _move(actions, reader, ("down", "up", "down", "down"), timing)
    _await_trainer_battle(actions, reader, timing)
    _run_battle(
        reader,
        actions,
        4,
        MapId.SILPH_CO_5F,
        "Silph 5F Rocket",
        RedBattlePlanId.SILPH_5F_ROCKET,
    )
    _require_event(emulator, EventFlag.BEAT_SILPH_CO_5F_TRAINER_0)
    _move(actions, reader, CARD_KEY_APPROACH, timing)
    _interact(actions, timing.dialogue_frames)
    if _bag(emulator).get(ItemId.CARD_KEY, 0) != 1:
        raise SilphChapterError("Card Key was not acquired.")
    _checkpoint(records, progress, emulator, reader.read(), "card_key", "Acquired Card Key")

    _move(actions, reader, CARD_KEY_RETURN, timing)
    _move(actions, reader, ("up", "up", "down", "up"), timing)
    _move(actions, reader, FIFTH_FLOOR_TO_ELEVATOR, timing)
    _move(actions, reader, ("up",), timing)
    _select_elevator_floor(actions, reader, emulator, 2, timing)
    _move(actions, reader, ELEVATOR_EXIT, timing)
    _move(actions, reader, THIRD_FLOOR_GUARD, timing)
    _await_trainer_battle(actions, reader, timing)
    _run_battle(
        reader,
        actions,
        4,
        MapId.SILPH_CO_3F,
        "Silph 3F Rocket",
        RedBattlePlanId.SILPH_3F_ROCKET,
    )
    _require_event(emulator, EventFlag.BEAT_SILPH_CO_3F_TRAINER_0)
    _move(actions, reader, ("down",), timing)
    _move(actions, reader, ("left",), timing)
    _interact(actions, timing.dialogue_frames)
    _confirm_many(actions, 4, timing.dialogue_frames)
    _require_event(emulator, EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "third_floor_door",
        "Opened required third-floor door",
    )

    _move(actions, reader, THIRD_FLOOR_TO_7F, timing)
    _move(actions, reader, ("down",), timing)
    _heal_detour_from_seventh(actions, reader, emulator, timing)
    _return_center_to_seventh(actions, reader, emulator, timing)
    _checkpoint(records, progress, emulator, reader.read(), "rival_ready", "Healed before rival")

    _move(actions, reader, _directions("ULL"), timing)
    _await_trainer_battle(actions, reader, timing)
    potion_before = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    _run_rival_with_potions(reader, actions, emulator, timing)
    potion_after = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    _require_event(emulator, EventFlag.BEAT_SILPH_CO_RIVAL)
    rival_potions_used = potion_before - potion_after
    if not 0 <= rival_potions_used <= 1:
        raise SilphChapterError(
            f"Rival policy consumed an invalid number of Hyper Potions: {rival_potions_used}."
        )
    _checkpoint(records, progress, emulator, reader.read(), "silph_rival", "Defeated Silph rival")

    _heal_detour_after_rival(actions, reader, emulator, timing)
    _return_center_to_seventh(actions, reader, emulator, timing)
    _move(actions, reader, SEVENT_TO_11F, timing)
    _require(reader.read(), MapId.SILPH_CO_11F, (3, 2), "Silph 11F")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "eleventh_ready",
        "Reached healed eleventh floor",
    )

    _move(actions, reader, ("down",) * 10, timing)
    _await_trainer_battle(actions, reader, timing)
    _run_battle(
        reader,
        actions,
        4,
        MapId.SILPH_CO_11F,
        "Silph 11F Rocket",
        RedBattlePlanId.SILPH_11F_ROCKET,
    )
    _require_event(emulator, EventFlag.BEAT_SILPH_CO_11F_TRAINER_0)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "eleventh_rocket",
        "Defeated required eleventh-floor Rocket",
    )

    _move(actions, reader, ROCKET_TO_11F_DOOR, timing)
    _interact(actions, timing.dialogue_frames)
    _confirm_many(actions, 3, timing.dialogue_frames)
    _require_event(emulator, EventFlag.SILPH_CO_11_UNLOCKED_DOOR)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "eleventh_door",
        "Opened boss-wing door",
    )

    _move(actions, reader, ("up", "up"), timing)
    _await_trainer_battle(actions, reader, timing)
    _run_battle(
        reader,
        actions,
        4,
        MapId.SILPH_CO_11F,
        "Silph Giovanni",
        RedBattlePlanId.SILPH_11F_GIOVANNI,
    )
    _require_event(emulator, EventFlag.BEAT_SILPH_CO_GIOVANNI)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "silph_liberated",
        "Defeated Giovanni and liberated Silph",
    )

    _move(actions, reader, GIOVANNI_TO_PRESIDENT, timing)
    _move(actions, reader, ("right",), timing)
    master_before = _bag(emulator).get(ItemId.MASTER_BALL, 0)
    _interact(actions, timing.menu_frames)
    for _ in range(16):
        if _bag(emulator).get(ItemId.MASTER_BALL, 0) == 1 and _event(
            emulator, EventFlag.GOT_MASTER_BALL
        ):
            break
        _confirm_many(actions, 1, timing.menu_frames)
    else:
        raise SilphChapterError("President dialogue exceeded its semantic bound.")
    master_after = _bag(emulator).get(ItemId.MASTER_BALL, 0)
    if master_before != 0 or master_after != 1:
        raise SilphChapterError("President did not award exactly one Master Ball.")
    _require_event(emulator, EventFlag.GOT_MASTER_BALL)
    _confirm_many(actions, 1, timing.menu_frames)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "master_ball",
        "Received Master Ball after liberation",
    )

    _move(actions, reader, PRESIDENT_TO_11F_WARP, timing)
    _move(actions, reader, ("down",), timing)
    _move(actions, reader, SEVENT_TO_THIRD_WARP, timing)
    _move(actions, reader, SEVENT_TO_THIRD, timing)
    _move(actions, reader, ("up",), timing)
    _select_elevator_floor(actions, reader, emulator, 0, timing)
    _move(actions, reader, ELEVATOR_EXIT, timing)
    _move(actions, reader, SILPH_1F_TO_EXIT, timing)
    _move(actions, reader, ("down",), timing)
    _move(actions, reader, CITY_TO_CENTER, timing)
    _move(actions, reader, ("up",), timing)
    _heal(actions, timing)
    final = reader.read()
    _require(final, MapId.SAFFRON_POKECENTER, (3, 3), "Silph terminal")
    _checkpoint(
        records,
        progress,
        emulator,
        final,
        "silph_terminal",
        "Healed liberated Saffron boundary",
    )

    required = tuple(
        (int(event), _event(emulator, event))
        for event in (
            EventFlag.BEAT_SILPH_CO_5F_TRAINER_0,
            EventFlag.BEAT_SILPH_CO_3F_TRAINER_0,
            EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2,
            EventFlag.BEAT_SILPH_CO_RIVAL,
            EventFlag.BEAT_SILPH_CO_11F_TRAINER_0,
            EventFlag.SILPH_CO_11_UNLOCKED_DOOR,
            EventFlag.BEAT_SILPH_CO_GIOVANNI,
            EventFlag.GOT_MASTER_BALL,
        )
    )
    report = SilphChapterReport(
        records=tuple(records),
        final_raw=final,
        money_before=money_before,
        money_after=_money(emulator),
        tm13_event=_event(emulator, EventFlag.GOT_TM13),
        tm13_transfer_before_event=tm13_transfer_ordered,
        other_roof_rewards_untouched=not _event(emulator, 0x18D) and not _event(emulator, 0x18E),
        fresh_water_after_reward=_bag(emulator).get(ItemId.FRESH_WATER, 0),
        tm13_after_teaching=_bag(emulator).get(ItemId.TM13_ICE_BEAM, 0),
        upgraded_moves=upgraded.first_party_moves or (),
        upgraded_pp=upgraded.first_party_pp or (),
        rival_potions_used=potion_before - potion_after,
        hyper_potions_remaining=_bag(emulator).get(ItemId.HYPER_POTION, 0),
        max_repel_remaining=_bag(emulator).get(ItemId.MAX_REPEL, 0),
        card_key_quantity=_bag(emulator).get(ItemId.CARD_KEY, 0),
        master_ball_quantity=_bag(emulator).get(ItemId.MASTER_BALL, 0),
        required_events=required,
        lapras_flag_before=lapras_before,
        lapras_flag_after=emulator.read_u8(STATUS_FLAGS_4),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        controller_released=not emulator.pressed_buttons,
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
    )
    if not report.passed:
        raise SilphChapterError("Silph evidence failed its terminal contract.")
    return report


def _acquire_and_teach_ice_beam(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> tuple[RawGameState, bool]:
    money_before = _money(emulator)
    _move(actions, reader, SAFFRON_CENTER_TO_ROUTE_7_GATE, timing)
    _require(reader.read(), MapId.ROUTE_7_GATE, (3, 4), "Route 7 gate east side")
    _move(actions, reader, ROUTE_7_GATE_TO_WEST, timing)
    _require(reader.read(), MapId.ROUTE_7, (11, 10), "Route 7 gate west exit")
    _move(actions, reader, ROUTE_7_WEST_TO_CONNECTION, timing)
    _require(reader.read(), MapId.ROUTE_7, (0, 3), "Route 7 west connection")
    _move(actions, reader, ROUTE_7_CONNECTION_TO_CELADON_CITY, timing)
    _require(reader.read(), MapId.CELADON_CITY, (10, 14), "Celadon City")
    _move(actions, reader, CELADON_CITY_TO_MART, timing)
    _require(reader.read(), MapId.CELADON_MART_1F, (16, 7), "Celadon Mart 1F")
    for route, map_id, coordinate, label in (
        (MART_1F_TO_2F, MapId.CELADON_MART_2F, (12, 2), "Celadon Mart 2F"),
        (MART_2F_TO_3F, MapId.CELADON_MART_3F, (16, 2), "Celadon Mart 3F"),
        (MART_3F_TO_4F, MapId.CELADON_MART_4F, (12, 2), "Celadon Mart 4F"),
        (MART_4F_TO_5F, MapId.CELADON_MART_5F, (16, 2), "Celadon Mart 5F"),
        (MART_5F_TO_ROOF, MapId.CELADON_MART_ROOF, (15, 3), "Celadon Mart roof"),
    ):
        _move(actions, reader, route, timing)
        for _ in range(4):
            if reader.read().map_id == map_id:
                break
            _move(actions, reader, route[-2:], timing)
        _require(reader.read(), map_id, coordinate, label)
    _require(reader.read(), MapId.CELADON_MART_ROOF, (15, 3), "Celadon Mart roof")
    _move(actions, reader, ROOF_TO_VENDING, timing)
    _require(reader.read(), MapId.CELADON_MART_ROOF, (12, 3), "roof vending stance")
    _pulse(actions, MacroActionKind.MOVE, timing, "up", timing.menu_frames)
    _interact(actions, timing.menu_frames)
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    _select_cursor(  # type: ignore[arg-type]
        actions,
        emulator,
        0,
        LavenderTiming(wait_frames=timing.menu_frames),
    )
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 0:
        raise SilphChapterError("Fresh Water was not vending cursor zero.")
    for _ in range(12):
        if (
            _bag(emulator).get(ItemId.FRESH_WATER, 0) == 1
            and _money(emulator) == money_before - FRESH_WATER_PRICE
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=1)
    else:
        raise SilphChapterError("Fresh Water purchase did not settle.")
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    _close_menus(  # type: ignore[arg-type]
        actions,
        reader,
        LavenderTiming(wait_frames=timing.menu_frames),
    )
    if not reader.read_input_readiness().ready:
        raise SilphChapterError("Vending dialogue did not restore field input.")

    _interact_with_roof_girl(actions, reader, emulator, timing)
    transfer_before_event = False
    for _ in range(240):
        water = _bag(emulator).get(ItemId.FRESH_WATER, 0)
        tm13 = _bag(emulator).get(ItemId.TM13_ICE_BEAM, 0)
        event = _event(emulator, EventFlag.GOT_TM13)
        if water == 0 and tm13 == 1 and not event:
            transfer_before_event = True
        if event and water == 0 and tm13 == 1 and transfer_before_event:
            break
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=1)
    else:
        raise SilphChapterError("Rooftop girl did not exchange Fresh Water for TM13.")
    if _event(emulator, 0x18D) or _event(emulator, 0x18E):
        raise SilphChapterError("A non-Ice-Beam rooftop reward event changed.")

    _teach_ice_beam(actions, reader, emulator, timing)
    _navigate_roof_to(actions, reader, emulator, (12, 3), timing)
    _return_roof_to_saffron(actions, reader, timing)
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "Saffron Center return")
    _move(actions, reader, ("up",) * 4, timing)
    _heal(actions, timing)
    for _ in range(24):
        upgraded = reader.read()
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and _party_status(emulator) == (0, 0, 0)
            and upgraded.first_party_moves == (0x82, 0x46, ICE_BEAM_MOVE, 0x39)
            and upgraded.first_party_pp == (15, 15, 10, 15)
            and reader.read_input_readiness().ready
        ):
            return upgraded, transfer_before_event
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    raise SilphChapterError("Ice Beam upgrade did not reach the healed Saffron boundary.")


def _return_roof_to_saffron(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SilphTiming,
) -> None:
    for route, map_id, coordinate, label in (
        (ROOF_TO_5F, MapId.CELADON_MART_5F, (12, 2), "roof to Mart 5F"),
        (MART_5F_TO_4F, MapId.CELADON_MART_4F, (16, 2), "Mart 4F return"),
        (MART_4F_TO_3F, MapId.CELADON_MART_3F, (12, 2), "Mart 3F return"),
        (MART_3F_TO_2F, MapId.CELADON_MART_2F, (16, 2), "Mart 2F return"),
        (MART_2F_TO_1F, MapId.CELADON_MART_1F, (12, 2), "Mart 1F return"),
        (MART_TO_CITY, MapId.CELADON_CITY, (10, 14), "Celadon Mart exit"),
    ):
        _move(actions, reader, route, timing)
        for _ in range(4):
            if reader.read().map_id == map_id:
                break
            _move(actions, reader, route[-2:], timing)
        _require(reader.read(), map_id, coordinate, label)
    _move(actions, reader, _directions("RRRRU"), timing)
    _confirm_many(actions, 3, timing.menu_frames)
    _clear_field_text(  # type: ignore[arg-type]
        actions,
        reader,
        LavenderTiming(wait_frames=timing.menu_frames),
    )
    _move(actions, reader, ("up",) * 2 + ("right",) * 36, timing)
    _require(reader.read(), MapId.ROUTE_7, (0, 3), "Route 7 return")
    _move(actions, reader, ROUTE_7_TO_GATE, timing)
    _require(reader.read(), MapId.ROUTE_7_GATE, (0, 4), "Route 7 gate return")
    _move(actions, reader, ("right",) * 3 + GATE_TO_SAFFRON, timing)
    _require(reader.read(), MapId.SAFFRON_CITY, (1, 18), "Saffron west entry")
    _move(actions, reader, SAFFRON_TO_CENTER, timing)


def _roof_girl_coordinate(emulator: EmulatorState) -> tuple[int, int]:
    return emulator.read_u8(ROOF_GIRL_X) - 4, emulator.read_u8(ROOF_GIRL_Y) - 4


def _roof_nerd_coordinate(emulator: EmulatorState) -> tuple[int, int]:
    return emulator.read_u8(ROOF_NERD_X) - 4, emulator.read_u8(ROOF_NERD_Y) - 4


def _interact_with_roof_girl(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    for _ in range(64):
        raw = reader.read()
        if raw.map_id != MapId.CELADON_MART_ROOF:
            raise SilphChapterError("Rooftop girl approach left the roof.")
        player = (raw.player_x or 0, raw.player_y or 0)
        girl = _roof_girl_coordinate(emulator)
        adjacent = frozenset(_adjacent_roof_tiles(girl))
        if player in adjacent:
            direction = _direction_between(player, girl)
            _pulse(actions, MacroActionKind.MOVE, timing, direction, timing.movement_frames)
            current = reader.read()
            current_player = (current.player_x or 0, current.player_y or 0)
            current_girl = _roof_girl_coordinate(emulator)
            if (
                current_player == player
                and abs(current_player[0] - current_girl[0])
                + abs(current_player[1] - current_girl[1])
                == 1
            ):
                _interact(actions, timing.menu_frames)
                return
        path = _bounded_roof_path(
            player,
            adjacent,
            frozenset({girl, _roof_nerd_coordinate(emulator)}),
        )
        if not path:
            raise SilphChapterError(
                f"No collision-safe rooftop path from {player!r} to girl {girl!r}."
            )
        _move(actions, reader, (path[0],), timing)
    raise SilphChapterError("Could not reach a live adjacent stance for the rooftop girl.")


def _navigate_roof_to(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    target: tuple[int, int],
    timing: SilphTiming,
) -> None:
    for _ in range(64):
        raw = reader.read()
        player = (raw.player_x or 0, raw.player_y or 0)
        if player == target:
            return
        blocked = frozenset({_roof_girl_coordinate(emulator), _roof_nerd_coordinate(emulator)})
        path = _bounded_roof_path(player, frozenset({target}), blocked)
        if not path:
            raise SilphChapterError(
                f"No collision-safe rooftop path from {player!r} to {target!r}."
            )
        _move(actions, reader, (path[0],), timing)
    raise SilphChapterError(
        f"Could not navigate from the rooftop girl to {target!r}; "
        f"girl={_roof_girl_coordinate(emulator)!r}."
    )


def _adjacent_roof_tiles(coordinate: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    x, y = coordinate
    return tuple(
        tile for tile in ((x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)) if tile in ROOF_WALKABLE
    )


def _bounded_roof_path(
    start: tuple[int, int],
    targets: frozenset[tuple[int, int]],
    blocked: frozenset[tuple[int, int]],
) -> tuple[str, ...]:
    allowed = ROOF_WALKABLE - blocked
    if start not in ROOF_WALKABLE:
        raise SilphChapterError(f"Rooftop BFS started off collision map at {start!r}.")
    queue = deque(((start, ()),))
    visited = {start}
    directions = (
        ("up", (0, -1)),
        ("left", (-1, 0)),
        ("right", (1, 0)),
        ("down", (0, 1)),
    )
    while queue:
        coordinate, path = queue.popleft()
        if coordinate in targets:
            return path
        for direction, (dx, dy) in directions:
            neighbor = coordinate[0] + dx, coordinate[1] + dy
            if neighbor in allowed and neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, (*path, direction)))
    return ()


def _direction_between(start: tuple[int, int], end: tuple[int, int]) -> str:
    delta = (end[0] - start[0], end[1] - start[1])
    return {
        (0, -1): "up",
        (0, 1): "down",
        (-1, 0): "left",
        (1, 0): "right",
    }[delta]


def _teach_ice_beam(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    menu_timing = LavenderTiming(wait_frames=timing.menu_frames)
    _open_bag(actions, emulator, menu_timing)  # type: ignore[arg-type]
    _select_bag_item(  # type: ignore[arg-type]
        actions,
        emulator,
        ItemId.TM13_ICE_BEAM,
        menu_timing,
    )
    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (0, 1):
            break
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    else:
        raise SilphChapterError("TM13 did not reach party selection.")
    _select_cursor(actions, emulator, 0, menu_timing)  # type: ignore[arg-type]
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (5, 8):
            break
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    else:
        raise SilphChapterError("TM13 did not reach move deletion.")
    _select_cursor(actions, emulator, 2, menu_timing)  # type: ignore[arg-type]
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    for _ in range(24):
        raw = reader.read()
        if raw.first_party_moves == (
            0x82,
            0x46,
            ICE_BEAM_MOVE,
            0x39,
        ) and ItemId.TM13_ICE_BEAM not in _bag(emulator):
            _close_menus(actions, reader, menu_timing)  # type: ignore[arg-type]
            return
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    raise SilphChapterError("TM13 did not replace BubbleBeam and consume the TM.")


def _buy_supplies(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    lavender_timing = LavenderTiming(wait_frames=timing.menu_frames)
    _pulse(actions, MacroActionKind.MOVE, timing, "left", timing.menu_frames)
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    _buy_mart_item(
        actions,  # type: ignore[arg-type]
        emulator,
        lavender_timing,
        absolute_index=1,
        item=ItemId.HYPER_POTION,
        quantity=HYPER_POTION_PURCHASE_QUANTITY,
        target_bag_quantity=HYPER_POTION_PURCHASE_QUANTITY,
    )
    _buy_mart_item(
        actions,  # type: ignore[arg-type]
        emulator,
        lavender_timing,
        absolute_index=2,
        item=ItemId.MAX_REPEL,
        quantity=1,
        target_bag_quantity=1,
    )
    _close_menus(
        actions,  # type: ignore[arg-type]
        reader,
        lavender_timing,
    )


def _select_elevator_floor(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    target: int,
    timing: SilphTiming,
) -> None:
    if reader.read().map_id != MapId.SILPH_CO_ELEVATOR:
        raise SilphChapterError("Elevator selection started outside the elevator.")
    _move(actions, reader, ELEVATOR_TO_PANEL, timing)
    _move(actions, reader, ("up",), timing)
    _interact(actions, timing.dialogue_frames)
    for _ in range(16):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        if absolute == target:
            break
        _pulse(
            actions,
            MacroActionKind.MOVE,
            timing,
            "down" if absolute < target else "up",
            timing.menu_frames,
        )
    else:
        raise SilphChapterError(f"Could not select elevator floor {target + 1}.")
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.dialogue_frames)


def _run_battle(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    move_slot: int,
    map_id: int,
    label: str,
    battle_plan_id: str,
    resource_policy: BattleResourcePolicy = (
        BattleResourcePolicy.NO_ADDITIONAL_CONSTRAINT
    ),
) -> None:
    run_adaptive_trainer_battle(
        reader,
        actions,
        lambda _: move_slot,
        expected_map=int(map_id),
        intent=BattleIntent(
            "liberate_silph",
            battle_plan_id=battle_plan_id,
            resource_policy=resource_policy,
        ),
        timing=BattleRuntimeTiming(max_runtime_pulses=720),
        label=label,
        unknown_cancel_interval=3,
    )


class _PauseBattle(Exception):
    pass


def _run_until(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    policy: Callable[[RawGameState], int],
    pause: Callable[[RawGameState], bool],
    label: str,
    battle_plan_id: str,
) -> bool:
    def guarded(raw: RawGameState) -> int:
        if pause(raw):
            raise _PauseBattle
        return policy(raw)

    try:
        run_adaptive_trainer_battle(
            reader,
            actions,
            guarded,
            expected_map=int(MapId.SILPH_CO_7F),
            intent=BattleIntent(
                "liberate_silph",
                battle_plan_id=battle_plan_id,
                resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
            ),
            timing=BattleRuntimeTiming(max_runtime_pulses=720),
            label=label,
            unknown_cancel_interval=3,
        )
    except BattleRuntimeError as error:
        if not isinstance(error.__cause__, _PauseBattle):
            raise
        return False
    return True


def _run_rival_with_potions(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    def policy(raw: RawGameState) -> int:
        if raw.enemy_species_id in {151, 154}:
            return 3
        return 2 if raw.enemy_species_id == 22 else 4

    completed = _run_until(
        reader,
        actions,
        policy,
        lambda raw: raw.enemy_species_id == 154,
        "Silph rival to Venusaur",
        RedBattlePlanId.SILPH_7F_RIVAL,
    )
    if completed:
        raise SilphChapterError("Rival battle ended before the Venusaur gate.")
    if (reader.read().first_party_hp or 0) < 110:
        _battle_hyper_potion(reader, actions, emulator, timing)
    _run_battle(
        reader,
        actions,
        3,
        MapId.SILPH_CO_7F,
        "Silph rival Venusaur",
        RedBattlePlanId.SILPH_7F_RIVAL,
        BattleResourcePolicy.BOUNDED_RECOVERY,
    )


def _battle_hyper_potion(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    _battle_healing_item(
        reader,
        actions,
        emulator,
        timing,
        ItemId.HYPER_POTION,
    )


def _battle_healing_item(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    emulator: EmulatorState,
    timing: SilphTiming,
    item: ItemId,
) -> None:
    if item not in {ItemId.HYPER_POTION, ItemId.FULL_RESTORE, ItemId.FULL_HEAL}:
        raise ValueError("battle healing item must be Hyper Potion, Full Restore, or Full Heal")
    label = item.name.replace("_", " ").title()
    raw = reader.read()
    menu = reader.read_battle_menu_state(raw)
    if raw.battle_state != 2 or menu.phase is not BattleMenuPhase.MAIN:
        raise SilphChapterError(f"{label} gate requires the trainer MAIN menu.")
    command = menu.selected_main_command
    if command == 0:
        _pulse(
            actions,
            MacroActionKind.MOVE,
            timing,
            "down",
            timing.battle_item_menu_frames,
        )
    elif command == 2:
        _pulse(
            actions,
            MacroActionKind.MOVE,
            timing,
            "left",
            timing.battle_item_menu_frames,
        )
        _pulse(
            actions,
            MacroActionKind.MOVE,
            timing,
            "down",
            timing.battle_item_menu_frames,
        )
    elif command == 3:
        _pulse(
            actions,
            MacroActionKind.MOVE,
            timing,
            "left",
            timing.battle_item_menu_frames,
        )
    elif command != 1:
        raise SilphChapterError("Invalid battle command cursor.")
    selected = reader.read_battle_menu_state(reader.read())
    if selected.selected_main_command != 1:
        raise SilphChapterError("Could not select the English ITEM battle command.")
    before = _bag(emulator).get(item, 0)
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.battle_item_frames)
    _select_bag_item(
        actions,  # type: ignore[arg-type]
        emulator,
        item,
        LavenderTiming(wait_frames=timing.menu_frames),
    )
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.battle_item_frames)
    for _ in range(6):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 0:
            break
        _pulse(
            actions,
            MacroActionKind.MOVE,
            timing,
            "up",
            timing.battle_item_menu_frames,
        )
    else:
        raise SilphChapterError("Could not select the party lead.")
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.battle_item_frames)
    for _ in range(24):
        current = reader.read()
        if (
            current.battle_state == 2
            and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.battle_item_frames)
    else:
        raise SilphChapterError(f"{label} did not return to the MAIN battle menu.")
    after = _bag(emulator).get(item, 0)
    if before - after != 1:
        raise SilphChapterError(f"{label} quantity did not decrement exactly once.")


def _heal_detour_from_seventh(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    _move(actions, reader, ("up", "down"), timing)
    _move(actions, reader, SEVENT_TO_THIRD, timing)
    _move(actions, reader, ("up",), timing)
    _select_elevator_floor(actions, reader, emulator, 0, timing)
    _move(actions, reader, ELEVATOR_EXIT, timing)
    _move(actions, reader, SILPH_1F_TO_EXIT, timing)
    _move(actions, reader, ("down",), timing)
    _move(actions, reader, CITY_TO_CENTER, timing)
    _move(actions, reader, ("up",), timing)
    _heal(actions, timing)


def _heal_detour_after_rival(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    _move(actions, reader, _directions("RRD"), timing)
    _move(actions, reader, SEVENT_TO_THIRD, timing)
    _move(actions, reader, ("up",), timing)
    _select_elevator_floor(actions, reader, emulator, 0, timing)
    _move(actions, reader, ELEVATOR_EXIT, timing)
    _move(actions, reader, SILPH_1F_TO_EXIT, timing)
    _move(actions, reader, ("down",), timing)
    _move(actions, reader, CITY_TO_CENTER, timing)
    _move(actions, reader, ("up",), timing)
    _heal(actions, timing)


def _return_center_to_seventh(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    _move(actions, reader, CENTER_EXIT, timing)
    _move(actions, reader, _directions("LLLLLLUUUUUUUURRRRRRRRRRRRRRRU"), timing)
    _move(actions, reader, SILPH_1F_TO_ELEVATOR, timing)
    _select_elevator_floor(actions, reader, emulator, 2, timing)
    _move(actions, reader, ELEVATOR_EXIT, timing)
    _move(actions, reader, THIRD_TO_SEVENT, timing)


def _await_trainer_battle(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SilphTiming,
) -> None:
    for _ in range(timing.max_script_pulses):
        if reader.read().battle_state == 2:
            return
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.dialogue_frames)
    raise SilphChapterError("Scripted trainer battle did not start inside its bound.")


def _heal(actions: _CountingExecutor, timing: SilphTiming) -> None:
    _confirm_many(actions, timing.heal_pulses, timing.menu_frames)


def _confirm_many(actions: _CountingExecutor, count: int, frames: int) -> None:
    for _ in range(count):
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _interact(actions: _CountingExecutor, frames: int) -> None:
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _pulse(
    actions: _CountingExecutor,
    kind: MacroActionKind,
    timing: SilphTiming,
    direction: str | None = None,
    frames: int | None = None,
) -> None:
    del timing
    actions.execute(MacroAction(kind, direction))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames or 1))


def _move(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    timing: SilphTiming,
) -> RawGameState:
    state = reader.read()
    for direction in directions:
        actions.execute(MacroAction(MacroActionKind.MOVE, direction))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.movement_frames))
        state = reader.read()
        if state.battle_state:
            break
    return state


def _require(
    raw: RawGameState,
    map_id: int,
    coordinate: tuple[int, int],
    label: str,
) -> None:
    if raw.map_id != map_id or (raw.player_x, raw.player_y) != coordinate:
        raise SilphChapterError(
            f"{label} expected map {int(map_id):#04x} at {coordinate}, got "
            f"{raw.map_id!r} at {(raw.player_x, raw.player_y)}."
        )


def _event(emulator: EmulatorState, event: int) -> bool:
    value = int(event)
    return bool(emulator.read_u8(int(RamAddress.EVENT_FLAGS) + value // 8) & (1 << (value % 8)))


def _require_event(emulator: EmulatorState, event: int) -> None:
    if not _event(emulator, event):
        raise SilphChapterError(f"Required event {int(event):#05x} is not set.")


def _checkpoint(
    records: list[SilphCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(SilphCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            SilphProgress(
                checkpoint_id=checkpoint_id,
                label=label,
                completed=len(records),
                total=SILPH_CHECKPOINT_COUNT,
                frames_executed=emulator.frame_count,
            )
        )
