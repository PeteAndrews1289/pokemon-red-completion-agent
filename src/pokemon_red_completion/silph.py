"""Qualified Silph Co. liberation chapter.

The routes, required trainers, scripted battles, and event IDs are pinned to
pret/pokered commit ``1e96034092686d006e863cace09e87273051a3d8``.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    note_observed_trainer_battle_exit,
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
    CITY_TO_MART as CELADON_CENTER_EXIT_TO_MART,
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
    SAFFRON_TO_CENTER,
)
from pokemon_red_completion.tower import party_core_intact

SILPH_CHECKPOINT_COUNT = 12
X_ACCURACY_REPLACEMENT_PRICE = 950
SILPH_NET_MONEY_DELTA = -2_301 - X_ACCURACY_REPLACEMENT_PRICE
SILPH_PREINSTALLED_TM13_NET_MONEY_DELTA = SILPH_NET_MONEY_DELTA + FRESH_WATER_PRICE
HYPER_POTION_PURCHASE_QUANTITY = 7
HYPER_POTION_PRICE = 1_500
X_SPECIAL_PURCHASE_QUANTITY = 3
SILPH_RIVAL_RECOVERY_HP = 80
SILPH_PC_DEPOSIT_ITEMS = (ItemId.SS_TICKET, ItemId.LIFT_KEY, ItemId.HELIX_FOSSIL)
STATUS_FLAGS_4 = 0xD72E
GOT_LAPRAS_MASK = 0x01
ICE_BEAM_MOVE = 0x3A
ROOF_GIRL_Y = 0xC224
ROOF_GIRL_X = 0xC225
ROOF_NERD_Y = 0xC214
ROOF_NERD_X = 0xC215
MART_2F_GIRL_Y = 0xC244
MART_2F_GIRL_X = 0xC245
MART_5F_GENTLEMAN_BLOCK_POSITION = (15, 2)
MART_5F_GENTLEMAN_YIELD_POSITION = (15, 3)
MART_5F_GENTLEMAN_CLEAR_POSITION = (14, 2)
MART_5F_GENTLEMAN_CLEAR_ATTEMPTS = 16
SAFFRON_CITY_SIZE = (40, 36)
SAFFRON_CENTER_APPROACH = (9, 30)
SAFFRON_WARP_COORDINATES = frozenset(
    {
        (7, 5),
        (26, 3),
        (34, 3),
        (13, 11),
        (25, 11),
        (18, 21),
        (9, 29),
        (29, 29),
    }
)
ROOF_STEP_FRAMES = 24
ROOF_PURSUIT_STEP_FRAMES = 24
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
MART_TO_CLERK = _directions("UUL")
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
ROUTE_7_CONNECTION_TO_GATE = _reverse(ROUTE_7_WEST_TO_CONNECTION)
ROUTE_7_CONNECTION_TO_CELADON_CITY = _reverse(CITY_TO_ROUTE_7)
CELADON_CITY_TO_LEFT_MART = ("left", "left", "up")
MART_LEFT_1F_TO_2F = ("right",) * 10 + ("up",) * 6
CELADON_MART_EXIT_TO_CENTER = _reverse(CELADON_CENTER_EXIT_TO_MART[:-1]) + ("up",)
ROOF_TO_SAFFRON_CENTER = (
    ROOF_TO_5F
    + MART_5F_TO_4F
    + MART_4F_TO_3F
    + MART_3F_TO_2F
    + MART_2F_TO_1F
    + MART_TO_CITY
    + CITY_TO_ROUTE_7
    + ROUTE_7_CONNECTION_TO_GATE
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
    movement_retries: int = 4
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
BATTLE_ITEM_SETTLE_PULSES = 720


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
    tm13_preinstalled: bool
    tm13_transfer_before_event: bool
    other_roof_rewards_untouched: bool
    fresh_water_after_reward: int
    tm13_after_teaching: int
    upgraded_moves: tuple[int, int, int, int]
    upgraded_pp: tuple[int, int, int, int]
    rival_potions_used: int
    rival_x_special_used: int
    hyper_potions_remaining: int
    max_repel_remaining: int
    route_items_archived: bool
    card_key_quantity: int
    master_ball_quantity: int
    required_events: tuple[tuple[int, bool], ...]
    lapras_flag_before: int
    lapras_flag_after: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
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
            and (self.tm13_preinstalled or self.tm13_transfer_before_event)
            and not (self.tm13_preinstalled and self.tm13_transfer_before_event)
            and self.other_roof_rewards_untouched
            and self.fresh_water_after_reward == 0
            and self.tm13_after_teaching == 0
            and self.upgraded_moves == (0x82, 0x46, ICE_BEAM_MOVE, 0x39)
            and self.upgraded_pp == (15, 15, 10, 15)
            and self.money_before >= 0
            and self.money_after
            == self.money_before
            + (
                SILPH_PREINSTALLED_TM13_NET_MONEY_DELTA
                if self.tm13_preinstalled
                else SILPH_NET_MONEY_DELTA
            )
            and 0 <= self.rival_potions_used <= 2
            and self.rival_x_special_used == 1
            and self.hyper_potions_remaining
            == HYPER_POTION_PURCHASE_QUANTITY - self.rival_potions_used
            and self.max_repel_remaining == 0
            and self.route_items_archived
            and self.card_key_quantity == 1
            and self.master_ball_quantity == 1
            and self.lapras_flag_before & GOT_LAPRAS_MASK == 0
            and self.lapras_flag_after & GOT_LAPRAS_MASK == 0
            and self.final_raw.map_id == MapId.SAFFRON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.battle_state == 0
            and party_core_intact(self.final_raw.party_species_ids)
            and self.final_raw.first_party_moves == (0x82, 0x46, ICE_BEAM_MOVE, 0x39)
            and self.final_raw.first_party_pp == (15, 15, 10, 15)
            and self.party_hp == self.party_max_hp
            and all(status == 0 for status in self.party_status)
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
                "preinstalled_before_silph": self.tm13_preinstalled,
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
                "x_special_used_by_rival_policy": self.rival_x_special_used,
                "remaining": self.hyper_potions_remaining,
                "max_repel_bought": 0,
                "max_repel_remaining": self.max_repel_remaining,
            },
            "inventory_capacity": {
                "archived_before_silph": [item.name for item in SILPH_PC_DEPOSIT_ITEMS],
                "transition_verified": self.route_items_archived,
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
    tm13_preinstalled = (
        _event(emulator, EventFlag.GOT_TM13)
        and initial.first_party_moves == (0x82, 0x46, ICE_BEAM_MOVE, 0x39)
        and initial.first_party_pp == (15, 15, 10, 15)
    )
    if (
        initial_bag.get(ItemId.CARD_KEY, 0)
        or initial_bag.get(ItemId.MASTER_BALL, 0)
        or initial_bag.get(ItemId.HYPER_POTION, 0)
        or initial_bag.get(ItemId.FRESH_WATER, 0)
        or initial_bag.get(ItemId.TM13_ICE_BEAM, 0)
        or (_event(emulator, EventFlag.GOT_TM13) and not tm13_preinstalled)
        or _event(emulator, 0x18D)
        or _event(emulator, 0x18E)
        or lapras_before & GOT_LAPRAS_MASK
    ):
        raise SilphChapterError("Silph input boundary is not pristine.")
    _checkpoint(records, progress, emulator, initial, "silph_ready", "Silph plan ready")
    route_items_archived = _store_spent_route_items(actions, reader, emulator, timing)

    # The roof exchange temporarily needs one free bag slot. Complete and
    # consume that item chain before adding the Hyper Potion stack.
    if tm13_preinstalled:
        upgraded = reader.read()
        tm13_transfer_ordered = False
    else:
        upgraded, tm13_transfer_ordered = _acquire_and_teach_ice_beam(
            actions,
            reader,
            emulator,
            timing,
        )

    # X Special is a Silph-rival resource, not part of Erika's earlier TM13
    # preparation.  Keep its purchase inside this chapter so the shared
    # Celadon Ice Beam route remains deterministic for Erika.
    _acquire_silph_x_special(actions, reader, emulator, timing)

    _move(actions, reader, CENTER_EXIT, timing)
    _navigate_saffron_coordinate(
        actions,
        reader,
        timing,
        (25, 12),
        "Saffron Mart",
    )
    _move_verified(actions, reader, MART_DOOR, timing, "Saffron Mart entry")
    _require(reader.read(), MapId.SAFFRON_MART, (3, 7), "Saffron Mart")
    _move(actions, reader, MART_TO_CLERK, timing)
    _buy_supplies(actions, reader, emulator, timing)
    if _bag(emulator).get(ItemId.HYPER_POTION, 0) != HYPER_POTION_PURCHASE_QUANTITY:
        raise SilphChapterError("Silph supply purchase failed.")
    _require(reader.read(), MapId.SAFFRON_MART, (2, 5), "Saffron clerk return")
    _move_verified(actions, reader, CLERK_TO_EXIT, timing, "Saffron Mart exit approach")
    _move_verified(actions, reader, ("down",), timing, "Saffron Mart exit warp")
    _navigate_saffron_center_approach(actions, reader, timing)
    _move_verified(actions, reader, ("up",), timing, "Saffron Center entry")
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "Saffron supply return")
    _move(actions, reader, ("up",) * 4, timing)
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
    x_special_before = _bag(emulator).get(ItemId.X_SPECIAL, 0)
    _run_rival_with_potions(reader, actions, emulator, timing)
    potion_after = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    _require_event(emulator, EventFlag.BEAT_SILPH_CO_RIVAL)
    rival_potions_used = potion_before - potion_after
    if not 0 <= rival_potions_used <= 2:
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
        tm13_preinstalled=tm13_preinstalled,
        tm13_transfer_before_event=tm13_transfer_ordered,
        other_roof_rewards_untouched=not _event(emulator, 0x18D) and not _event(emulator, 0x18E),
        fresh_water_after_reward=_bag(emulator).get(ItemId.FRESH_WATER, 0),
        tm13_after_teaching=_bag(emulator).get(ItemId.TM13_ICE_BEAM, 0),
        upgraded_moves=upgraded.first_party_moves or (),
        upgraded_pp=upgraded.first_party_pp or (),
        rival_potions_used=potion_before - potion_after,
        rival_x_special_used=x_special_before - _bag(emulator).get(ItemId.X_SPECIAL, 0),
        hyper_potions_remaining=_bag(emulator).get(ItemId.HYPER_POTION, 0),
        max_repel_remaining=_bag(emulator).get(ItemId.MAX_REPEL, 0),
        route_items_archived=route_items_archived,
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
    _clear_field_text(
        actions,
        reader,
        LavenderTiming(wait_frames=timing.menu_frames),
    )
    _move_verified(actions, reader, CELADON_CITY_TO_LEFT_MART, timing, "Celadon Mart entry")
    _require(reader.read(), MapId.CELADON_MART_1F, (2, 7), "Celadon Mart 1F")
    for route, map_id, coordinate, label in (
        (MART_LEFT_1F_TO_2F, MapId.CELADON_MART_2F, (12, 2), "Celadon Mart 2F"),
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
    transfer_before_event = _acquire_and_teach_ice_beam_on_roof(
        actions,
        reader,
        emulator,
        timing,
        money_before=money_before,
    )
    _navigate_roof_to(actions, reader, emulator, (12, 3), timing)
    _return_roof_to_saffron(actions, reader, timing)
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "Saffron Center return")
    _move(actions, reader, ("up",) * 4, timing)
    _heal(actions, timing)
    for _ in range(24):
        upgraded = reader.read()
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and all(status == 0 for status in _party_status(emulator))
            and upgraded.first_party_moves == (0x82, 0x46, ICE_BEAM_MOVE, 0x39)
            and upgraded.first_party_pp == (15, 15, 10, 15)
            and reader.read_input_readiness().ready
        ):
            return upgraded, transfer_before_event
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    raise SilphChapterError("Ice Beam upgrade did not reach the healed Saffron boundary.")


def acquire_and_teach_ice_beam_from_celadon_center(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    timing: SilphTiming = DEFAULT_SILPH_TIMING,
) -> tuple[RawGameState, bool]:
    """Install Ice Beam and return through the Center's entrance while still healed."""

    _require(reader.read(), MapId.CELADON_POKECENTER, (3, 3), "Celadon Ice Beam boundary")
    if _party_hp(emulator) != _party_max_hp(emulator) or any(
        status != 0 for status in _party_status(emulator)
    ):
        raise SilphChapterError("Celadon Ice Beam boundary requires a healed party.")
    money_before = _money(emulator)
    _move(actions, reader, CENTER_EXIT, timing)
    _require(reader.read(), MapId.CELADON_CITY, (41, 10), "Celadon Center exit")
    _move(actions, reader, CELADON_CENTER_EXIT_TO_MART, timing)
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
    transfer_before_event = _acquire_and_teach_ice_beam_on_roof(
        actions,
        reader,
        emulator,
        timing,
        money_before=money_before,
    )
    _navigate_roof_to(actions, reader, emulator, (12, 3), timing)
    _move(actions, reader, ROOF_TO_5F, timing)
    _require(reader.read(), MapId.CELADON_MART_5F, (12, 2), "roof to Mart 5F")
    for route, map_id, coordinate, label in (
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
    _move(actions, reader, CELADON_MART_EXIT_TO_CENTER, timing)
    _require(reader.read(), MapId.CELADON_POKECENTER, (3, 7), "Celadon Center return")
    for _ in range(24):
        upgraded = reader.read()
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and all(status == 0 for status in _party_status(emulator))
            and upgraded.first_party_moves == (0x82, 0x46, ICE_BEAM_MOVE, 0x39)
            and upgraded.first_party_pp == (15, 15, 10, 15)
            and reader.read_input_readiness().ready
        ):
            return upgraded, transfer_before_event
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    raise SilphChapterError("Ice Beam upgrade did not reach the healed Celadon entrance boundary.")


def _buy_silph_x_special(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    menu_timing = LavenderTiming(wait_frames=timing.menu_frames)
    _require(reader.read(), MapId.CELADON_MART_5F, (16, 2), "Silph X Special boundary")
    _move_verified(
        actions,
        reader,
        _directions("LLLLLLLLDDDDLLLU"),
        timing,
        "X Special clerk approach",
    )
    _require(reader.read(), MapId.CELADON_MART_5F, (5, 5), "X Special clerk approach")
    _pulse(actions, MacroActionKind.MOVE, timing, "up", timing.menu_frames)
    # The clerk is reached across the counter: this pulse faces north but the
    # counter correctly keeps the player at (5, 5).
    _require(reader.read(), MapId.CELADON_MART_5F, (5, 5), "X Special clerk stance")
    _interact(actions, timing.menu_frames)
    _select_cursor(actions, emulator, 0, menu_timing)  # type: ignore[arg-type]
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    _buy_mart_item(
        actions,  # type: ignore[arg-type]
        emulator,
        menu_timing,
        absolute_index=6,
        item=ItemId.X_SPECIAL,
        quantity=X_SPECIAL_PURCHASE_QUANTITY,
        target_bag_quantity=X_SPECIAL_PURCHASE_QUANTITY,
    )
    _buy_mart_item(
        actions,  # type: ignore[arg-type]
        emulator,
        menu_timing,
        absolute_index=0,
        item=ItemId.X_ACCURACY,
        quantity=1,
        target_bag_quantity=1,
    )
    _close_menus(actions, reader, menu_timing)  # type: ignore[arg-type]
    _move_verified(
        actions,
        reader,
        _directions("DRRRUUUURRRRRRRR"),
        timing,
        "X Special clerk return",
    )
    _require(reader.read(), MapId.CELADON_MART_5F, (16, 2), "Silph X Special return")


def _acquire_silph_x_special(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    """Buy one Silph and two Sabrina X Specials and restore the Center boundary."""

    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 3), "Silph X Special start")
    _move(actions, reader, SAFFRON_CENTER_TO_ROUTE_7_GATE, timing)
    _require(reader.read(), MapId.ROUTE_7_GATE, (3, 4), "X Special Route 7 gate east side")
    _move(actions, reader, ROUTE_7_GATE_TO_WEST, timing)
    _require(reader.read(), MapId.ROUTE_7, (11, 10), "X Special Route 7 gate west exit")
    _move(actions, reader, ROUTE_7_WEST_TO_CONNECTION, timing)
    _require(reader.read(), MapId.ROUTE_7, (0, 3), "X Special Route 7 west connection")
    _move(actions, reader, ROUTE_7_CONNECTION_TO_CELADON_CITY, timing)
    _require(reader.read(), MapId.CELADON_CITY, (10, 14), "X Special Celadon City")
    _clear_field_text(
        actions,
        reader,
        LavenderTiming(wait_frames=timing.menu_frames),
    )
    _move_verified(actions, reader, CELADON_CITY_TO_LEFT_MART, timing, "X Special Mart entry")
    _require(reader.read(), MapId.CELADON_MART_1F, (2, 7), "X Special Mart 1F")
    for route, map_id, coordinate, label in (
        (MART_LEFT_1F_TO_2F, MapId.CELADON_MART_2F, (12, 2), "X Special Mart 2F"),
        (MART_2F_TO_3F, MapId.CELADON_MART_3F, (16, 2), "X Special Mart 3F"),
        (MART_3F_TO_4F, MapId.CELADON_MART_4F, (12, 2), "X Special Mart 4F"),
        (MART_4F_TO_5F, MapId.CELADON_MART_5F, (16, 2), "X Special Mart 5F"),
    ):
        _move_verified(actions, reader, route, timing, label)
        _require(reader.read(), map_id, coordinate, label)
    _buy_silph_x_special(actions, reader, emulator, timing)
    for route, map_id, coordinate, label in (
        (("up",), MapId.CELADON_MART_4F, (16, 2), "X Special Mart 4F return"),
        (MART_4F_TO_3F, MapId.CELADON_MART_3F, (12, 2), "X Special Mart 3F return"),
        (MART_3F_TO_2F, MapId.CELADON_MART_2F, (16, 2), "X Special Mart 2F return"),
        (MART_TO_CITY, MapId.CELADON_CITY, (10, 14), "X Special Celadon Mart exit"),
    ):
        if map_id == MapId.CELADON_CITY:
            _return_mart_2f_to_1f(actions, reader, emulator, timing)
        _move_verified(actions, reader, route, timing, label)
        _require(reader.read(), map_id, coordinate, label)
    _move(actions, reader, _directions("RRRRU"), timing)
    _confirm_many(actions, 3, timing.menu_frames)
    _clear_field_text(  # type: ignore[arg-type]
        actions,
        reader,
        LavenderTiming(wait_frames=timing.menu_frames),
    )
    _move(actions, reader, ("up",) * 2 + ("right",) * 36, timing)
    _require(reader.read(), MapId.ROUTE_7, (0, 3), "X Special Route 7 return")
    _move(actions, reader, ROUTE_7_CONNECTION_TO_GATE, timing)
    _require(reader.read(), MapId.ROUTE_7, (11, 10), "X Special Route 7 gate exterior")
    _move(actions, reader, ("right",), timing)
    _require(reader.read(), MapId.ROUTE_7_GATE, (0, 4), "X Special Route 7 gate return")
    _move(actions, reader, ("right",) * 3 + GATE_TO_SAFFRON, timing)
    _require(reader.read(), MapId.SAFFRON_CITY, (1, 18), "X Special Saffron west entry")
    _move(actions, reader, SAFFRON_TO_CENTER, timing)
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "X Special Saffron return")
    _move(actions, reader, ("up",) * 4, timing)
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 3), "X Special restored boundary")
    if _bag(emulator).get(ItemId.X_SPECIAL, 0) != X_SPECIAL_PURCHASE_QUANTITY:
        raise SilphChapterError("Silph X Special purchase failed.")


def _acquire_and_teach_ice_beam_on_roof(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
    *,
    money_before: int,
) -> bool:
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
    intermediate_transfer_observed = False
    transfer_before_event = False
    for _ in range(480):
        water = _bag(emulator).get(ItemId.FRESH_WATER, 0)
        tm13 = _bag(emulator).get(ItemId.TM13_ICE_BEAM, 0)
        event = _event(emulator, EventFlag.GOT_TM13)
        if water == 0 and tm13 == 1 and not event:
            intermediate_transfer_observed = True
        if event and water == 0 and tm13 == 1:
            # The pinned CeladonMartRoof script removes the drink, gives TM13,
            # prints the reward text, and only then sets EVENT_GOT_TM13. Host
            # sampling may observe that intermediate state or both writes may
            # settle between consecutive observations.
            transfer_before_event = True
            break
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=1)
    else:
        raise SilphChapterError(
            "Rooftop girl did not exchange Fresh Water for TM13: "
            f"water={water}, tm13={tm13}, event={event}, "
            f"intermediate={intermediate_transfer_observed}."
        )
    if _event(emulator, 0x18D) or _event(emulator, 0x18E):
        raise SilphChapterError("A non-Ice-Beam rooftop reward event changed.")

    _clear_field_text(  # type: ignore[arg-type]
        actions,
        reader,
        LavenderTiming(wait_frames=timing.menu_frames),
    )
    _teach_ice_beam(actions, reader, emulator, timing)
    return transfer_before_event


def _store_spent_route_items(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> bool:
    before = _bag(emulator)
    # A held-out battle schedule may consume the final item in a recovery
    # stack, legitimately reducing the number of occupied slots.  Capacity is
    # the semantic requirement: depositing these three obsolete route items
    # must leave at most sixteen slots so the roof reward, supplies, Card Key,
    # and Master Ball can all be received later.
    deposit_items = _silph_capacity_deposit_items(before)
    if deposit_items is None:
        route_quantities = {item.name: before.get(item, 0) for item in SILPH_PC_DEPOSIT_ITEMS}
        raise SilphChapterError(
            "Silph capacity cleanup lacks room or the spent route items: "
            f"slots={len(before)}, candidates={route_quantities}."
        )
    if not deposit_items:
        return True
    expected_slots = len(before) - len(deposit_items)
    _move(actions, reader, ("down",) + ("right",) * 10, timing)
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (13, 4), "pre-Silph PC approach")
    for item in deposit_items:
        _deposit_pc_item(actions, reader, emulator, item, timing)
    after = _bag(emulator)
    if (
        len(after) != expected_slots
        or len(after) > 16
        or any(item in after for item in deposit_items)
        or not reader.read_input_readiness().ready
    ):
        raise SilphChapterError("Pre-Silph PC cleanup did not establish safe bag capacity.")
    _move(actions, reader, ("left",) * 10 + ("up",), timing)
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 3), "pre-Silph PC return")
    return True


def _silph_capacity_ready(bag: Mapping[object, int]) -> bool:
    """Prove current capacity or an available obsolete-item cleanup can reach it."""

    return _silph_capacity_deposit_items(bag) is not None


def _silph_capacity_deposit_items(
    bag: Mapping[object, int],
) -> tuple[ItemId, ...] | None:
    """Select only the available obsolete items needed for a sixteen-slot boundary."""

    # Koga consumes the Tower X Accuracy against Muk.  This chapter replaces
    # it during the 5F battle-item purchase, so a missing copy at entry needs
    # one reserved future slot before Card Key and Master Ball are awarded.
    replacement_slots = 0 if bag.get(ItemId.X_ACCURACY, 0) else 1
    slots_to_free = max(0, len(bag) + replacement_slots - 16)
    available = tuple(item for item in SILPH_PC_DEPOSIT_ITEMS if bag.get(item, 0) == 1)
    if len(available) < slots_to_free:
        return None
    return available[:slots_to_free]


def _deposit_pc_item(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    item: ItemId,
    timing: SilphTiming,
) -> None:
    _pulse(actions, MacroActionKind.MOVE, timing, "up", timing.menu_frames)
    _pulse(actions, MacroActionKind.INTERACT, timing, frames=timing.menu_frames)
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    _select_pc_menu_cursor(actions, emulator, 1, timing)
    for _ in range(3):
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 0:
        raise SilphChapterError("Saffron PC did not expose WITHDRAW ITEM.")
    _pulse(actions, MacroActionKind.MOVE, timing, "down", timing.menu_frames)
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    _select_pc_bag_item(actions, emulator, item, timing)
    for _ in range(3):
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    if item in _bag(emulator):
        raise SilphChapterError(f"Saffron PC did not store {item.name}.")
    for _ in range(4):
        _pulse(actions, MacroActionKind.CANCEL, timing, frames=timing.menu_frames)
    if not reader.read_input_readiness().ready:
        raise SilphChapterError(f"Saffron PC did not close after storing {item.name}.")


def _select_pc_menu_cursor(
    actions: _CountingExecutor,
    emulator: EmulatorState,
    target: int,
    timing: SilphTiming,
) -> None:
    for _ in range(16):
        current = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if current == target:
            return
        _pulse(
            actions,
            MacroActionKind.MOVE,
            timing,
            "down" if current < target else "up",
            timing.menu_frames,
        )
    raise SilphChapterError(f"PC menu could not select cursor {target}.")


def _select_pc_bag_item(
    actions: _CountingExecutor,
    emulator: EmulatorState,
    item: ItemId,
    timing: SilphTiming,
) -> None:
    for _ in range(24):
        items = tuple(_bag(emulator))
        if item not in items:
            raise SilphChapterError(f"Required PC item {item.name} is unavailable.")
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        target = items.index(item)
        if absolute == target:
            return
        _pulse(
            actions,
            MacroActionKind.MOVE,
            timing,
            "down" if absolute < target else "up",
            timing.menu_frames,
        )
    raise SilphChapterError(f"Could not select PC item {item.name}.")


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
    # The original eastbound shortcut crosses the one-way south ledge at
    # (9, 3). Reusing it after the changed rooftop cadence can collide above
    # the ledge and consume the remainder of a fixed route. Reverse the
    # source-derived lower-corridor path instead; it contains no ledge jump.
    _move(actions, reader, ROUTE_7_CONNECTION_TO_GATE, timing)
    _require(reader.read(), MapId.ROUTE_7, (11, 10), "Route 7 gate exterior")
    _move(actions, reader, ("right",), timing)
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
    *,
    reward_started: Callable[[], bool] | None = None,
) -> None:
    if reward_started is None:

        def observed_reward_started() -> bool:
            return (
                _bag(emulator).get(ItemId.FRESH_WATER, 0) == 0
                or _bag(emulator).get(ItemId.TM13_ICE_BEAM, 0) == 1
                or _event(emulator, EventFlag.GOT_TM13)
            )
    else:
        observed_reward_started = reward_started
    for attempt in range(1024):
        raw = reader.read()
        if raw.map_id != MapId.CELADON_MART_ROOF:
            raise SilphChapterError("Rooftop girl approach left the roof.")
        player = (raw.player_x or 0, raw.player_y or 0)
        girl = _roof_girl_coordinate(emulator)
        adjacent = frozenset(_adjacent_roof_tiles(girl))
        if player in adjacent:
            direction = _direction_between(player, girl)
            _pulse(actions, MacroActionKind.MOVE, timing, direction, 1)
            # A one-frame facing pulse is enough for a walking object to move.
            # Only send A when the fresh observation still has the girl on the
            # tile being faced; otherwise resume pursuit from the new state.
            faced_raw = reader.read()
            faced_player = (faced_raw.player_x or 0, faced_raw.player_y or 0)
            faced_girl = _roof_girl_coordinate(emulator)
            if (
                faced_player not in _adjacent_roof_tiles(faced_girl)
                or _direction_between(faced_player, faced_girl) != direction
            ):
                continue
            _interact(actions, timing.menu_frames)
            if observed_reward_started() or not reader.read_input_readiness().ready:
                return
            # Text-box state is not represented by InputReadiness on every
            # frame. If dialogue did open, another observed A press advances
            # it; the inventory/event transition above is the authoritative
            # success signal. If the NPC moved, the next iteration replans.
            continue
        path = _bounded_roof_path(
            player,
            adjacent,
            frozenset({girl, _roof_nerd_coordinate(emulator)}),
        )
        if not path:
            raise SilphChapterError(
                f"No collision-safe rooftop path from {player!r} to girl {girl!r}."
            )
        # Break deterministic lockstep when both sprites keep advancing on the
        # same movement cadence. The varying bounded wait changes only the
        # pursuit phase; every subsequent step is still replanned from RAM.
        _pulse(
            actions,
            MacroActionKind.WAIT,
            timing,
            frames=1 + attempt % 11,
        )
        _pulse(actions, MacroActionKind.MOVE, timing, path[0], ROOF_PURSUIT_STEP_FRAMES)
    final = reader.read()
    raise SilphChapterError(
        "Could not reach a live adjacent stance for the rooftop girl: "
        f"player={(final.player_x, final.player_y)!r}, "
        f"girl={_roof_girl_coordinate(emulator)!r}."
    )


def _navigate_roof_to(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    target: tuple[int, int],
    timing: SilphTiming,
) -> None:
    for _ in range(256):
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
        _pulse(actions, MacroActionKind.MOVE, timing, path[0], ROOF_STEP_FRAMES)
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
    for _ in range(timing.movement_retries):
        _pulse(actions, MacroActionKind.MOVE, timing, "left", timing.menu_frames)
        raw = reader.read()
        if (
            raw.map_id == MapId.SAFFRON_MART
            and (raw.player_x, raw.player_y) == (2, 5)
            and emulator.read_u8(RamAddress.PLAYER_FACING_DIRECTION) == 0x08
        ):
            break
    else:
        raw = reader.read()
        raise SilphChapterError(
            "Saffron clerk interaction stance was not established: "
            f"position={(raw.player_x, raw.player_y)!r}, "
            f"facing={emulator.read_u8(RamAddress.PLAYER_FACING_DIRECTION):#04x}, "
            f"front={emulator.read_u8(RamAddress.TILE_IN_FRONT_OF_PLAYER):#04x}, "
            f"joy_ignore={emulator.read_u8(RamAddress.JOY_IGNORE):#04x}."
        )
    _pulse(actions, MacroActionKind.INTERACT, timing, frames=timing.menu_frames)
    for _ in range(8):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (5, 4):
            break
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    else:
        raise SilphChapterError("Saffron clerk did not open the priced item list.")
    _buy_mart_item(
        actions,  # type: ignore[arg-type]
        emulator,
        lavender_timing,
        absolute_index=1,
        item=ItemId.HYPER_POTION,
        quantity=HYPER_POTION_PURCHASE_QUANTITY,
        target_bag_quantity=HYPER_POTION_PURCHASE_QUANTITY,
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
    move_slot: int | Callable[[RawGameState], int],
    map_id: int,
    label: str,
    battle_plan_id: str,
    resource_policy: BattleResourcePolicy = (BattleResourcePolicy.NO_ADDITIONAL_CONSTRAINT),
) -> None:
    policy = move_slot if callable(move_slot) else lambda _: move_slot
    run_adaptive_trainer_battle(
        reader,
        actions,
        policy,
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
    potion_start = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    _battle_x_special(reader, actions, emulator, timing)
    recovery = 0
    forced_switches = 0
    while recovery < min(2, potion_start):
        try:
            completed = _run_until(
                reader,
                actions,
                _silph_rival_move_slot,
                lambda raw: 0 < (raw.battler_hp or 0) <= SILPH_RIVAL_RECOVERY_HP,
                f"Silph rival bounded recovery {recovery + 1}",
                RedBattlePlanId.SILPH_7F_RIVAL,
            )
        except BattleRuntimeError:
            raw = reader.read()
            if raw.battle_state == 0:
                note_observed_trainer_battle_exit(_silph_rival_intent())
                _settle_silph_rival_field_control(reader, actions, timing)
                return
            party_hp = _party_hp(emulator)
            if (
                raw.battle_state != 2
                or raw.battler_hp != 0
                or forced_switches >= 4
                or not any(hp > 0 for hp in party_hp)
            ):
                raise
            terminal = _settle_silph_rival_forced_switch(reader, actions, emulator, timing)
            if terminal:
                note_observed_trainer_battle_exit(_silph_rival_intent())
                _settle_silph_rival_field_control(reader, actions, timing)
                return
            forced_switches += 1
            continue
        if completed:
            return
        _battle_hyper_potion(reader, actions, emulator, timing)
        recovery += 1
    # Exhausting the healing allocation does not revoke the balanced-party
    # contract.  Continue with living reserves through the same verified
    # forced-switch path, but never spend a third potion or reset the switch
    # bound merely because recovery is exhausted.
    while True:
        try:
            _run_battle(
                reader,
                actions,
                _silph_rival_move_slot,
                MapId.SILPH_CO_7F,
                "Silph rival Venusaur exhausted recovery",
                RedBattlePlanId.SILPH_7F_RIVAL,
                BattleResourcePolicy.BOUNDED_RECOVERY,
            )
            return
        except BattleRuntimeError:
            raw = reader.read()
            if raw.battle_state == 0:
                note_observed_trainer_battle_exit(_silph_rival_intent())
                _settle_silph_rival_field_control(reader, actions, timing)
                return
            party_hp = _party_hp(emulator)
            if (
                raw.battle_state != 2
                or raw.battler_hp != 0
                or forced_switches >= 4
                or not any(hp > 0 for hp in party_hp)
            ):
                raise
            terminal = _settle_silph_rival_forced_switch(reader, actions, emulator, timing)
            if terminal:
                note_observed_trainer_battle_exit(_silph_rival_intent())
                _settle_silph_rival_field_control(reader, actions, timing)
                return
            forced_switches += 1


def _silph_rival_move_slot(raw: RawGameState) -> int:
    if raw.active_party_index not in {None, 0}:
        pp = raw.battler_pp or ()
        for slot in (1, 2, 3, 4):
            if len(pp) >= slot and pp[slot - 1] & 0x3F:
                return slot
        raise SilphChapterError("Silph rival reserve battler has no usable move.")
    if raw.enemy_species_id in {151, 154}:
        priorities = (3, 4, 2, 1)
    elif raw.enemy_species_id == 22:
        priorities = (3, 2, 4, 1)
    else:
        priorities = (4, 2, 3, 1)
    pp = raw.first_party_pp or ()
    for slot in priorities:
        if (
            len(pp) >= slot
            and pp[slot - 1] & 0x3F
            and not (raw.player_disabled_move_slot == slot and (raw.player_disable_turns or 0) > 0)
        ):
            return slot
    raise SilphChapterError("Silph rival policy has no legal move with PP.")


def _silph_rival_intent() -> BattleIntent:
    return BattleIntent(
        "liberate_silph",
        battle_plan_id=RedBattlePlanId.SILPH_7F_RIVAL,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
    )


def _settle_silph_rival_field_control(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    timing: SilphTiming,
) -> None:
    """Clear terminal rival text and prove stable field input before routing."""

    ready_reads = 0
    for _ in range(48):
        raw = reader.read()
        if raw.battle_state != 0:
            raise SilphChapterError("Silph rival terminal recovery re-entered battle.")
        if reader.read_input_readiness().ready:
            ready_reads += 1
            if ready_reads >= 2:
                return
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.menu_frames))
        else:
            ready_reads = 0
            _pulse(
                actions,
                MacroActionKind.CONFIRM,
                timing,
                frames=timing.dialogue_frames,
            )
    raise SilphChapterError("Silph rival terminal text did not restore field control.")


def _settle_silph_rival_forced_switch(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> bool:
    """Select the healthiest reserve after a rival KO and prove battle MAIN."""

    hp = _party_hp(emulator)
    active = reader.read().active_party_index
    candidates = [index for index, value in enumerate(hp) if value > 0 and index != active]
    if not candidates:
        raise SilphChapterError("Silph rival KO left no healthy reserve.")
    target = max(candidates, key=lambda index: hp[index])
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
            raise SilphChapterError("Silph rival forced switch left the battle.")
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        _pulse(
            actions,
            MacroActionKind.CONFIRM if cursor == target else MacroActionKind.MOVE,
            timing,
            None if cursor == target else ("down" if cursor < target else "up"),
            timing.menu_frames,
        )
        if pulse_index % 5 == 4:
            # Faint text precedes the forced party screen and ignores cursor
            # movement. Periodic confirmation advances only that bounded
            # dialogue; once the party screen appears the cursor proof above
            # remains authoritative.
            _pulse(
                actions,
                MacroActionKind.CONFIRM,
                timing,
                frames=timing.menu_frames,
            )
    raise SilphChapterError("Silph rival forced switch exceeded its bounded menu pulses.")


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


def _battle_x_special(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    for _ in range(timing.max_script_pulses):
        raw = reader.read()
        menu = reader.read_battle_menu_state(raw)
        if raw.battle_state != 2:
            raise SilphChapterError("Silph X Special left the trainer battle intro.")
        if menu.phase is BattleMenuPhase.MAIN:
            break
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.dialogue_frames)
    else:
        raise SilphChapterError("Silph X Special did not reach the trainer MAIN menu.")
    command = menu.selected_main_command
    if command == 0:
        _pulse(actions, MacroActionKind.MOVE, timing, "down", timing.battle_item_menu_frames)
    elif command == 2:
        _pulse(actions, MacroActionKind.MOVE, timing, "left", timing.battle_item_menu_frames)
        _pulse(actions, MacroActionKind.MOVE, timing, "down", timing.battle_item_menu_frames)
    elif command == 3:
        _pulse(actions, MacroActionKind.MOVE, timing, "left", timing.battle_item_menu_frames)
    elif command != 1:
        raise SilphChapterError("Silph X Special exposed an invalid battle command cursor.")
    if reader.read_battle_menu_state(reader.read()).selected_main_command != 1:
        raise SilphChapterError("Silph X Special could not select ITEM.")
    before = _bag(emulator).get(ItemId.X_SPECIAL, 0)
    if before < 1:
        raise SilphChapterError(f"Silph X Special reserve mismatch: {before!r}.")
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.battle_item_frames)
    _select_bag_item(
        actions,  # type: ignore[arg-type]
        emulator,
        ItemId.X_SPECIAL,
        LavenderTiming(wait_frames=timing.menu_frames),
    )
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.battle_item_frames)
    for _ in range(BATTLE_ITEM_SETTLE_PULSES):
        current = reader.read()
        if (
            current.battle_state == 2
            and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.battle_item_frames)
    else:
        raise SilphChapterError("Silph X Special did not return to MAIN.")
    if _bag(emulator).get(ItemId.X_SPECIAL, 0) != before - 1:
        raise SilphChapterError("Silph X Special did not decrement exactly once.")


def _battle_healing_item(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    emulator: EmulatorState,
    timing: SilphTiming,
    item: ItemId,
    *,
    _retry: bool = False,
) -> bool:
    """Use one healing item and report whether the item turn ended the battle."""
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
    for _ in range(BATTLE_ITEM_SETTLE_PULSES):
        current = reader.read()
        after = _bag(emulator).get(item, 0)
        if (
            current.battle_state == 2
            and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
        ):
            break
        if _battle_healing_item_verified_terminal_exit(current, before, after):
            # An opponent can faint from recoil on the item turn. In that
            # case there is no MAIN menu to return to even though the item was
            # consumed and the trainer battle ended successfully.
            return True
        # CANCEL advances Gen I battle text but is inert on MAIN. Sampling after
        # each frame therefore tolerates long enemy replies without confirming
        # ITEM again during the first observable MAIN frame.
        _pulse(actions, MacroActionKind.CANCEL, timing, frames=1)
    else:
        # The final bounded CANCEL can itself complete the enemy reply and
        # expose MAIN.  Observe that post-action state before declaring the
        # wait exhausted; otherwise a legitimate transition on the last pulse
        # is rejected even though the semantic target has been reached.
        current = reader.read()
        phase = reader.read_battle_menu_state(current).phase
        if current.battle_state != 2 or phase is not BattleMenuPhase.MAIN:
            raise SilphChapterError(
                f"{label} did not return to the MAIN battle menu: "
                f"battle_state={current.battle_state}, phase={phase.value}, "
                f"hp={current.battler_hp}/{current.battler_max_hp}, "
                f"quantity={_bag(emulator).get(item, 0)}."
            )
    after = _bag(emulator).get(item, 0)
    if before - after == 1:
        return False
    current = reader.read()
    current_menu = reader.read_battle_menu_state(current)
    if (
        before == after
        and not _retry
        and current.battle_state == 2
        and current_menu.phase is BattleMenuPhase.MAIN
        and 0 < (current.first_party_hp or 0) < (current.first_party_max_hp or 0)
    ):
        # A long battle animation can occasionally return to MAIN without the
        # party-target confirmation registering. Retry the complete semantic
        # item action once; the unchanged quantity proves no item was spent.
        return _battle_healing_item(
            reader,
            actions,
            emulator,
            timing,
            item,
            _retry=True,
        )
    raise SilphChapterError(
        f"{label} quantity did not decrement exactly once: "
        f"before={before}, after={after}, retry={_retry}, "
        f"hp={current.first_party_hp}/{current.first_party_max_hp}, "
        f"phase={current_menu.phase.value}."
    )


def _battle_healing_item_verified_terminal_exit(
    raw: RawGameState,
    quantity_before: int,
    quantity_after: int,
) -> bool:
    """Recognize an item turn whose enemy recoil legitimately ended battle."""

    return (
        raw.battle_state == 0
        and raw.enemy_hp == 0
        and quantity_before - quantity_after == 1
    )


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


def _move_verified(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    timing: SilphTiming,
    label: str,
) -> RawGameState:
    """Advance only after each requested step has an observed world-state effect."""
    state = reader.read()
    for index, direction in enumerate(tuple(directions), 1):
        before = state
        for _ in range(timing.movement_retries):
            state = _move(actions, reader, (direction,), timing)
            if state.battle_state:
                raise SilphChapterError(f"{label} entered an unexpected battle.")
            if (
                state.map_id != before.map_id
                or state.player_x != before.player_x
                or state.player_y != before.player_y
            ):
                break
        else:
            if (
                label == "X Special clerk approach"
                and before.map_id == MapId.CELADON_MART_5F
                and (before.player_x, before.player_y) == MART_5F_GENTLEMAN_BLOCK_POSITION
                and direction == "left"
            ):
                state = _yield_to_mart_5f_gentleman(actions, reader, timing)
                continue
            raise SilphChapterError(
                f"{label} blocked at step {index}: {direction}; "
                f"{(state.map_id, state.player_x, state.player_y)!r}."
            )
    return state


def _yield_to_mart_5f_gentleman(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SilphTiming,
) -> RawGameState:
    """Yield the top aisle so the source-pinned vertical customer can pass."""

    for attempt in range(MART_5F_GENTLEMAN_CLEAR_ATTEMPTS):
        state = reader.read()
        if (state.player_x, state.player_y) == MART_5F_GENTLEMAN_CLEAR_POSITION:
            return state
        _require(
            state,
            MapId.CELADON_MART_5F,
            MART_5F_GENTLEMAN_BLOCK_POSITION,
            "X Special customer gate",
        )
        actions.execute(MacroAction(MacroActionKind.MOVE, "down"))
        yielded = reader.read()
        _require(
            yielded,
            MapId.CELADON_MART_5F,
            MART_5F_GENTLEMAN_YIELD_POSITION,
            "X Special customer yield",
        )
        for return_attempt in range(MART_5F_GENTLEMAN_CLEAR_ATTEMPTS):
            actions.execute(
                MacroAction(
                    MacroActionKind.WAIT,
                    repeat=timing.movement_frames * (attempt + return_attempt + 1),
                )
            )
            actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
            returned = reader.read()
            if (returned.player_x, returned.player_y) == MART_5F_GENTLEMAN_BLOCK_POSITION:
                break
            _require(
                returned,
                MapId.CELADON_MART_5F,
                MART_5F_GENTLEMAN_YIELD_POSITION,
                "X Special customer return wait",
            )
        else:
            raise SilphChapterError("Celadon Mart 5F customer did not release the return tile.")
        actions.execute(MacroAction(MacroActionKind.MOVE, "left"))
        crossed = reader.read()
        if (crossed.player_x, crossed.player_y) == MART_5F_GENTLEMAN_CLEAR_POSITION:
            return crossed
        _require(
            crossed,
            MapId.CELADON_MART_5F,
            MART_5F_GENTLEMAN_BLOCK_POSITION,
            "X Special customer final gate",
        )
    raise SilphChapterError("Celadon Mart 5F customer did not clear the top aisle.")


def _return_mart_2f_to_1f(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    """Wait for the vertical customer, then cross the only open top aisle."""

    _require(reader.read(), MapId.CELADON_MART_2F, (16, 2), "X Special Mart 2F return")
    for _ in range(32):
        state = reader.read()
        if state.player_x == 12:
            break
        if (state.player_x, state.player_y) == (15, 2):
            _wait_for_mart_2f_customer(actions, emulator)
        try:
            _move_verified(actions, reader, ("left",), timing, "X Special Mart 2F top row")
        except SilphChapterError as error:
            current = reader.read()
            if (current.map_id, current.player_x, current.player_y) != (
                MapId.CELADON_MART_2F,
                15,
                2,
            ):
                raise error
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=17))
    else:
        raise SilphChapterError("X Special Mart 2F customer did not clear the top aisle.")
    _require(reader.read(), MapId.CELADON_MART_2F, (12, 2), "X Special Mart 2F stairs")
    _move_verified(actions, reader, ("up",), timing, "X Special Mart 1F return")
    _require(reader.read(), MapId.CELADON_MART_1F, (12, 2), "X Special Mart 1F return")


def _wait_for_mart_2f_customer(
    actions: _CountingExecutor,
    emulator: EmulatorState,
) -> None:
    """Observe the pinned vertical NPC rather than sampling it at a fixed cadence."""

    for _ in range(2_048):
        if _mart_2f_girl_coordinate(emulator) != (14, 2):
            return
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=1))
    raise SilphChapterError("Celadon Mart 2F customer did not clear the top aisle.")


def _mart_2f_girl_coordinate(emulator: EmulatorState) -> tuple[int, int]:
    return emulator.read_u8(MART_2F_GIRL_X) - 4, emulator.read_u8(MART_2F_GIRL_Y) - 4


def _plan_saffron_center_approach(
    start: tuple[int, int],
    blocked: frozenset[tuple[int, int]] = frozenset(),
) -> tuple[str, ...]:
    return _plan_saffron_route(start, SAFFRON_CENTER_APPROACH, blocked)


def _plan_saffron_route(
    start: tuple[int, int],
    target: tuple[int, int],
    blocked: frozenset[tuple[int, int]] = frozenset(),
) -> tuple[str, ...]:
    width, height = SAFFRON_CITY_SIZE
    if not 0 <= start[0] < width or not 0 <= start[1] < height:
        raise SilphChapterError(f"Saffron planner started out of bounds at {start!r}.")
    if not 0 <= target[0] < width or not 0 <= target[1] < height:
        raise SilphChapterError(f"Saffron planner target is out of bounds at {target!r}.")
    queue = deque([(start, ())])
    visited = {start}
    steps = (
        ("left", (-1, 0)),
        ("down", (0, 1)),
        ("right", (1, 0)),
        ("up", (0, -1)),
    )
    while queue:
        coordinate, route = queue.popleft()
        if coordinate == target:
            return route
        for direction, (dx, dy) in steps:
            candidate = (coordinate[0] + dx, coordinate[1] + dy)
            if (
                candidate in visited
                or candidate in blocked
                or candidate in SAFFRON_WARP_COORDINATES
                or not 0 <= candidate[0] < width
                or not 0 <= candidate[1] < height
            ):
                continue
            visited.add(candidate)
            queue.append((candidate, (*route, direction)))
    raise SilphChapterError(
        f"Saffron Center has no route after collision discoveries {sorted(blocked)!r}."
    )


def _navigate_saffron_center_approach(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SilphTiming,
) -> RawGameState:
    return _navigate_saffron_coordinate(
        actions,
        reader,
        timing,
        SAFFRON_CENTER_APPROACH,
        "Saffron Center",
    )


def _navigate_saffron_coordinate(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SilphTiming,
    target: tuple[int, int],
    label: str,
) -> RawGameState:
    """Discover static and moving Saffron obstacles while approaching a target."""
    state = reader.read()
    if state.map_id != MapId.SAFFRON_CITY or state.player_x is None or state.player_y is None:
        raise SilphChapterError("Saffron navigator lacks its city entry coordinate.")
    discovered_blocked: set[tuple[int, int]] = set()
    deltas = {"up": (0, -1), "left": (-1, 0), "right": (1, 0), "down": (0, 1)}
    for _ in range(500):
        start = (state.player_x, state.player_y)
        if start == target:
            return state
        route = _plan_saffron_route(start, target, frozenset(discovered_blocked))
        direction = route[0]
        dx, dy = deltas[direction]
        candidate = (start[0] + dx, start[1] + dy)
        for _ in range(timing.movement_retries):
            state = _move(actions, reader, (direction,), timing)
            if state.battle_state:
                raise SilphChapterError("Saffron navigation entered an unexpected battle.")
            if state.map_id != MapId.SAFFRON_CITY:
                raise SilphChapterError(
                    f"Saffron navigation entered unexpected map {state.map_id!r}."
                )
            if (state.player_x, state.player_y) != start:
                break
        else:
            discovered_blocked.add(candidate)
    raise SilphChapterError(f"{label} navigation exceeded its bounded collision discoveries.")


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
