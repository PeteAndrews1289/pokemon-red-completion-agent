"""Qualified Route 22, Victory Road, and Indigo Plateau preparation chapter.

Routes, boulder coordinates, switch events, and mart inventories are pinned to
pret/pokered commit ``1e96034092686d006e863cace09e87273051a3d8`` and verified
against the supported English Pokémon Red ROM.
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
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.blaine import _select_cursor
from pokemon_red_completion.celadon import (
    DEFAULT_CELADON_TIMING,
    _bag,
    _flee,
    _money,
    _party_hp,
    _party_max_hp,
    _party_status,
    _RunState,
)
from pokemon_red_completion.giovanni import _sell_current_bag_item
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _buy_mart_item,
    _close_menus,
    _open_bag,
    _select_bag_item,
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
from pokemon_red_completion.sabrina import SabrinaChapterError, _deposit_pc_item
from pokemon_red_completion.saffron import (
    CITY_TO_MART,
    MART_1F_TO_2F,
    MART_2F_TO_1F,
    MART_3F_TO_2F,
    MART_3F_TO_4F,
    MART_4F_TO_3F,
    MART_4F_TO_5F,
    MART_TO_CITY,
)
from pokemon_red_completion.silph import DEFAULT_SILPH_TIMING, _battle_hyper_potion
from pokemon_red_completion.tower import TOWER_FINAL_PARTY

VICTORY_ROAD_CHECKPOINT_COUNT = 9
RIVAL_PARTY = (
    (0x97, 47),
    (0x12, 45),
    (0x16, 45),
    (0x21, 47),
    (0x95, 50),
    (0x9A, 53),
)
RIVAL_POLICY = {
    0x97: 3,
    0x12: 4,
    0x16: 3,
    0x21: 4,
    0x95: 4,
    0x9A: 3,
}
BADGE_CHECK_EVENTS = (
    EventFlag.PASSED_CASCADE_BADGE_CHECK,
    EventFlag.PASSED_THUNDER_BADGE_CHECK,
    EventFlag.PASSED_RAINBOW_BADGE_CHECK,
    EventFlag.PASSED_SOUL_BADGE_CHECK,
    EventFlag.PASSED_MARSH_BADGE_CHECK,
    EventFlag.PASSED_VOLCANO_BADGE_CHECK,
    EventFlag.PASSED_EARTH_BADGE_CHECK,
)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "R": "right", "D": "down", "L": "left"}[item] for item in value)


CENTER_TO_ROUTE_22 = _directions("DDDDDLLUUUUUUUULLLLLULLLLLLLLLLLLLLLLL")
ROUTE_22_TO_RIVAL = _directions("LLDDDLLLLUUULLUUUUL")
SAFFRON_TO_MART = _directions("RRRRRDRURRRRRRRRRRRRRRRRRRRRRUUUUUUUUUUUUUUUUULLLLLLLULLLLU")
VIRIDIAN_TO_ROUTE_22 = _directions("LLUUUUUUUULLLLLULLLLLLLLLLLLLLLLL")
ROUTE_22_TO_GATE = _directions("LLDDDLLLLLULUUUUUULLLLLLLLLLDDDDDDLLLLLLLLLLLLLLLLUURRRRRRUUUULLLU")
THUNDER_APPROACH = _directions("UUUURRRRRRRUUUUUUUULLLLLUUUUL")
RAINBOW_APPROACH = _directions("UUURUUUUUUUUUURR")
MARSH_APPROACH = _directions("UUUUUUUUUULLL")
VOLCANO_APPROACH = _directions("UUUUUUUUUUUUURUUUUUURRUUUUUUUUUL")
EARTH_APPROACH = _directions("DRRURUUUUUUUULLLLUULUUUUUUUUUULLLL")
VR1_TO_2F = _directions("LDDLLLLLLLDDLLLLUUUURRRRRRUUUUUULLLLDDLLLLUUULUUUUL")
VR2_TO_3F = _directions("RUUUUURRUUURRRRRRRRRDDDDRRRDDRRRRDDRRRRRRRUUUUULLLLLUUUU")
VR3_SWITCH_TO_HOLE = _directions(
    "UUURRRRURRRRRRRRRRRRRRDDDDDLLLUULLLLLLLDDDDDDLLLLLUULLLLDDDDDDDRRRRRRRRRRDRRRURRRRRRR"
)
VR2_FINAL_TO_3F = _directions("RRRRRUURRRRRRRRRR")
VR3_SOUTHEAST_TO_2F = _directions("UUUUUULU")
ROUTE_23_TO_INDIGO = _directions("RRRRUUUUUUUUUUUULLLLUUUUUUUUUULUUUULLLUUUUUUU")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class VictoryRoadChapterError(RuntimeError):
    """Raised when the Victory Road evidence contract fails."""


@dataclass(frozen=True, slots=True)
class VictoryRoadProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[VictoryRoadProgress], None]


@dataclass(frozen=True, slots=True)
class VictoryRoadCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class RivalTurn:
    species: int
    level: int
    enemy_hp: int
    lead_hp: int
    pp: tuple[int, int, int, int]
    move_slot: int


@dataclass(frozen=True, slots=True)
class VictoryRoadChapterReport:
    records: tuple[VictoryRoadCheckpoint, ...]
    final_raw: RawGameState
    rival_turns: tuple[RivalTurn, ...]
    rival_party: tuple[tuple[int, int], ...]
    rival_potions_used: int
    badge_checks: tuple[bool, ...]
    vr1_switch_set: bool
    vr2_switch1_set: bool
    vr3_switch_set: bool
    vr3_hole_set: bool
    vr2_switch2_set: bool
    full_restores: int
    full_heals: int
    revives: int
    hyper_potions: int
    x_specials: int
    max_repels: int
    tm27_sold: bool
    tm38_sold: bool
    tm28_sold: bool
    tm06_consumed: bool
    party_hp: tuple[int, int, int]
    party_max_hp: tuple[int, int, int]
    party_status: tuple[int, int, int]
    money_remaining: int
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == VICTORY_ROAD_CHECKPOINT_COUNT
            and self.rival_party == RIVAL_PARTY
            and 0 <= self.rival_potions_used <= 11
            and _rival_moves_valid(self.rival_turns)
            and self.badge_checks == (True,) * 7
            and self.vr1_switch_set
            and self.vr2_switch1_set
            and self.vr3_switch_set
            and self.vr3_hole_set
            and self.vr2_switch2_set
            and self.full_restores == 13
            and self.full_heals == 3
            and self.revives == 2
            and self.hyper_potions == 11
            and self.x_specials == 6
            and self.max_repels == 0
            and self.tm27_sold
            and self.tm38_sold
            and self.tm28_sold
            and self.tm06_consumed
            and self.final_raw.map_id == MapId.INDIGO_PLATEAU_LOBBY
            and (self.final_raw.player_x, self.final_raw.player_y) == (2, 5)
            and self.final_raw.party_species_ids == TOWER_FINAL_PARTY
            and self.final_raw.first_party_level == 51
            and self.final_raw.first_party_moves == (0x42, 0x46, 0x3A, 0x39)
            and self.final_raw.first_party_pp == (25, 15, 10, 15)
            and self.party_hp == self.party_max_hp == (157, 47, 40)
            and self.party_status == (0, 0, 0)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "cross_victory_road",
            "route22_rival": {
                "party": [list(item) for item in self.rival_party],
                "turns": [
                    {
                        "species": item.species,
                        "level": item.level,
                        "enemy_hp": item.enemy_hp,
                        "lead_hp": item.lead_hp,
                        "pp": list(item.pp),
                        "move_slot": item.move_slot,
                    }
                    for item in self.rival_turns
                ],
                "hyper_potions_used": self.rival_potions_used,
            },
            "route23": {"badge_checks": list(self.badge_checks)},
            "switches": {
                "victory_road_1f": self.vr1_switch_set,
                "victory_road_2f_first": self.vr2_switch1_set,
                "victory_road_3f": self.vr3_switch_set,
                "victory_road_3f_hole": self.vr3_hole_set,
                "victory_road_2f_final": self.vr2_switch2_set,
            },
            "indigo_supplies": {
                "full_restores": self.full_restores,
                "full_heals": self.full_heals,
                "revives": self.revives,
                "hyper_potions": self.hyper_potions,
                "x_specials": self.x_specials,
                "max_repels": self.max_repels,
                "money_remaining": self.money_remaining,
            },
            "terminal": {
                "map": int(self.final_raw.map_id),
                "position": [self.final_raw.player_x, self.final_raw.player_y],
                "level": self.final_raw.first_party_level,
                "hp": list(self.party_hp),
                "max_hp": list(self.party_max_hp),
                "status": list(self.party_status),
                "pp": list(self.final_raw.first_party_pp or ()),
            },
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


def run_victory_road_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> VictoryRoadChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[VictoryRoadCheckpoint] = []
    wild_run = _RunState([])
    initial = reader.read()
    _require(initial, MapId.VIRIDIAN_POKECENTER, (3, 3), "Giovanni boundary")
    if (
        initial.badge_bits != 0xFF
        or not _event(initial, EventFlag.SECOND_ROUTE_22_RIVAL_BATTLE)
        or not _event(initial, EventFlag.ROUTE_22_RIVAL_WANTS_BATTLE)
        or _event(initial, EventFlag.BEAT_ROUTE_22_RIVAL_2ND_BATTLE)
        or not 1 <= _bag(emulator).get(ItemId.HYPER_POTION, 0) <= 6
    ):
        raise VictoryRoadChapterError("Victory Road input boundary is not qualified.")
    _checkpoint(
        records,
        progress,
        emulator,
        initial,
        "victory_road_ready",
        "Eight-badge route ready",
    )
    _teach_toxic(actions, reader, emulator)

    _move_with_wilds(
        actions,
        reader,
        emulator,
        wild_run,
        CENTER_TO_ROUTE_22,
        "Route 22 entry",
    )
    _require(reader.read(), MapId.ROUTE_22, (39, 9), "Route 22 entry")
    _move_with_wilds(
        actions,
        reader,
        emulator,
        wild_run,
        ROUTE_22_TO_RIVAL,
        "Route 22 rival approach",
    )
    _require(reader.read(), MapId.ROUTE_22, (30, 5), "Route 22 rival approach")
    if _party_hp(emulator)[0] < _party_max_hp(emulator)[0]:
        _use_bag_item(
            actions,
            reader,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            ItemId.HYPER_POTION,
        )

    _field_fly(actions, reader, emulator, "down", MapId.SAFFRON_CITY)
    _move(actions, reader, ("up",), "Saffron Center entry")
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "Saffron Center entry")
    _move(actions, reader, ("up",) * 4, "Saffron nurse")
    _heal(actions, reader, emulator)
    _move(actions, reader, ("down",) * 5, "Saffron Center exit")
    _move(actions, reader, SAFFRON_TO_MART, "Saffron Mart")
    _require(reader.read(), MapId.SAFFRON_MART, (3, 7), "Saffron Mart entry")
    _move(actions, reader, ("up", "left", "up"), "Saffron clerk")
    _pulse(actions, MacroActionKind.MOVE, "left", 120)
    _sell_current_bag_item(actions, emulator, ItemId.TM27_FISSURE)
    _pulse(actions, MacroActionKind.CANCEL)
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    current_hyper = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    hyper_purchase = 11 - current_hyper
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=1,
        item=ItemId.HYPER_POTION,
        quantity=hyper_purchase,
        target_bag_quantity=11,
    )
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=2,
        item=ItemId.MAX_REPEL,
        quantity=10,
        target_bag_quantity=10,
    )
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    supplied = reader.read()
    if (
        _bag(emulator).get(ItemId.HYPER_POTION, 0) != 11
        or _bag(emulator).get(ItemId.MAX_REPEL, 0) != 10
        or ItemId.TM27_FISSURE in _bag(emulator)
    ):
        raise VictoryRoadChapterError("Saffron resupply failed.")
    _checkpoint(records, progress, emulator, supplied, "victory_supplied", "Healed and resupplied")

    _move(actions, reader, ("right", "down", "down", "down"), "Saffron Mart exit")
    _field_fly(actions, reader, emulator, "up", MapId.VIRIDIAN_CITY)
    _move_with_wilds(
        actions,
        reader,
        emulator,
        wild_run,
        VIRIDIAN_TO_ROUTE_22,
        "Return to Route 22",
    )
    _require(reader.read(), MapId.ROUTE_22, (39, 9), "Resupplied Route 22 entry")
    _move_with_wilds(
        actions,
        reader,
        emulator,
        wild_run,
        ROUTE_22_TO_RIVAL,
        "Resupplied Route 22 rival approach",
    )
    _require(reader.read(), MapId.ROUTE_22, (30, 5), "Resupplied rival approach")
    if _party_hp(emulator)[0] < _party_max_hp(emulator)[0]:
        _use_bag_item(
            actions,
            reader,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            ItemId.HYPER_POTION,
        )
    rival_turns, rival_potions_used = _defeat_route22_rival(actions, reader, emulator)
    rival_party = _encounter_party(rival_turns)
    rival_raw = reader.read()
    if (
        rival_party != RIVAL_PARTY
        or not _event(rival_raw, EventFlag.BEAT_ROUTE_22_RIVAL_2ND_BATTLE)
        or _event(rival_raw, EventFlag.ROUTE_22_RIVAL_WANTS_BATTLE)
    ):
        raise VictoryRoadChapterError("Route 22 rival evidence changed.")
    _checkpoint(
        records,
        progress,
        emulator,
        rival_raw,
        "route22_rival",
        "Defeated final route rival",
    )

    _field_fly(actions, reader, emulator, "down", MapId.SAFFRON_CITY)
    _move(actions, reader, ("up",), "Saffron recovery entry")
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "Saffron recovery entry")
    _move(actions, reader, ("up",) * 4, "Saffron recovery nurse")
    _heal(actions, reader, emulator)
    _archive_silph_scope(actions, reader, emulator)
    _move(actions, reader, ("down",) * 5, "Saffron recovery exit")
    _move(actions, reader, SAFFRON_TO_MART, "Saffron recovery Mart")
    _require(reader.read(), MapId.SAFFRON_MART, (3, 7), "Saffron recovery Mart entry")
    _move(actions, reader, ("up", "left", "up"), "Saffron recovery clerk")
    _pulse(actions, MacroActionKind.MOVE, "left", 120)
    _pulse(actions, MacroActionKind.INTERACT)
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    current_hyper = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    if current_hyper < 11:
        _buy_mart_item(
            actions,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            absolute_index=1,
            item=ItemId.HYPER_POTION,
        quantity=11 - current_hyper,
        target_bag_quantity=11,
        )
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    _sell_current_bag_item(actions, emulator, ItemId.TM24_THUNDERBOLT)
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    _sell_current_bag_item(actions, emulator, ItemId.TM21_MEGA_DRAIN)
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    _move(actions, reader, ("right", "down", "down", "down"), "Saffron recovery Mart exit")
    _acquire_and_teach_submission(actions, reader, emulator)
    _field_fly(actions, reader, emulator, "up", MapId.VIRIDIAN_CITY)
    _move_with_wilds(
        actions,
        reader,
        emulator,
        wild_run,
        VIRIDIAN_TO_ROUTE_22,
        "League return to Route 22",
    )
    _require(reader.read(), MapId.ROUTE_22, (39, 9), "League Route 22 entry")
    _move_with_wilds(
        actions,
        reader,
        emulator,
        wild_run,
        ROUTE_22_TO_GATE,
        "League reception gate",
    )
    _require(reader.read(), MapId.ROUTE_22_GATE, (4, 7), "League reception gate")
    for _ in range(5):
        _step(actions, reader, "up", "Boulder Badge gate")
    _settle_confirm(actions, reader, 12)
    for _ in range(3):
        if reader.read().map_id == MapId.ROUTE_23:
            break
        _step(actions, reader, "up", "Route 23 entry")
    _require(reader.read(), MapId.ROUTE_23, (7, 139), "Route 23 entry")

    _move_with_wilds(actions, reader, emulator, wild_run, ("up", "up"), "Cascade gate approach")
    _pass_badge_gate(
        actions,
        reader,
        emulator,
        wild_run,
        ("up",),
        EventFlag.PASSED_CASCADE_BADGE_CHECK,
    )
    _move_with_wilds(actions, reader, emulator, wild_run, THUNDER_APPROACH, "Thunder gate approach")
    _pass_badge_gate(
        actions,
        reader,
        emulator,
        wild_run,
        ("right", "up"),
        EventFlag.PASSED_THUNDER_BADGE_CHECK,
    )
    _move_with_wilds(actions, reader, emulator, wild_run, RAINBOW_APPROACH, "Rainbow gate approach")
    _pass_badge_gate(
        actions,
        reader,
        emulator,
        wild_run,
        ("left", "up"),
        EventFlag.PASSED_RAINBOW_BADGE_CHECK,
    )
    _move_with_wilds(actions, reader, emulator, wild_run, ("up", "left"), "Route 23 Surf shore")
    _field_surf(actions, reader, emulator)
    _move_with_wilds(actions, reader, emulator, wild_run, ("up",) * 6, "Soul gate approach")
    _pass_badge_gate(
        actions, reader, emulator, wild_run, ("up",), EventFlag.PASSED_SOUL_BADGE_CHECK
    )
    _move_with_wilds(actions, reader, emulator, wild_run, MARSH_APPROACH, "Marsh gate approach")
    _pass_badge_gate(
        actions, reader, emulator, wild_run, ("up",), EventFlag.PASSED_MARSH_BADGE_CHECK
    )
    _move_with_wilds(actions, reader, emulator, wild_run, VOLCANO_APPROACH, "Volcano gate approach")
    _pass_badge_gate(
        actions,
        reader,
        emulator,
        wild_run,
        ("up",),
        EventFlag.PASSED_VOLCANO_BADGE_CHECK,
    )
    _move_with_wilds(actions, reader, emulator, wild_run, EARTH_APPROACH, "Earth gate approach")
    _pass_badge_gate(
        actions, reader, emulator, wild_run, ("up",), EventFlag.PASSED_EARTH_BADGE_CHECK
    )
    badge_checks = tuple(_event(reader.read(), item) for item in BADGE_CHECK_EVENTS)
    if badge_checks != (True,) * 7:
        raise VictoryRoadChapterError(f"Route 23 badge checks changed: {badge_checks!r}.")
    _move_with_wilds(
        actions,
        reader,
        emulator,
        wild_run,
        _directions("URUUU"),
        "Victory Road entrance",
    )
    _require(reader.read(), MapId.VICTORY_ROAD_1F, (8, 17), "Victory Road 1F")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "badge_corridor",
        "Passed all badge gates",
    )

    _use_bag_item(actions, reader, emulator, DEFAULT_LAVENDER_TIMING, ItemId.MAX_REPEL)
    _activate_strength(actions, reader, emulator)
    vr1_route = (
        _directions("LULLLLLURRUR")
        + ("down", "left", "down")
        + ("right",) * 4
        + _directions("DRUU")
        + _directions("LU")
        + ("right",) * 7
        + _directions("DRUUDLLUURRURD")
    )
    _move(actions, reader, vr1_route, "Victory Road 1F switch")
    vr1_switch = _event(reader.read(), EventFlag.VICTORY_ROAD_1F_BOULDER_ON_SWITCH)
    if not vr1_switch:
        raise VictoryRoadChapterError("Victory Road 1F switch did not set.")
    _checkpoint(records, progress, emulator, reader.read(), "vr1_switch", "Opened 1F barrier")
    _move(actions, reader, VR1_TO_2F, "Victory Road 2F entry")
    _require(reader.read(), MapId.VICTORY_ROAD_2F, (0, 8), "Victory Road 2F")

    _activate_strength(actions, reader, emulator)
    _move(
        actions,
        reader,
        _directions("DRRRDDRRDDDLULDDRDLL"),
        "Victory Road 2F first switch",
    )
    vr2_switch1 = _event(reader.read(), EventFlag.VICTORY_ROAD_2F_BOULDER_ON_SWITCH_1)
    if not vr2_switch1:
        raise VictoryRoadChapterError("Victory Road 2F first switch did not set.")
    _checkpoint(records, progress, emulator, reader.read(), "vr2_switch", "Opened 2F barrier")
    _move(actions, reader, VR2_TO_3F, "Victory Road 3F entry")
    _require(reader.read(), MapId.VICTORY_ROAD_3F, (23, 7), "Victory Road 3F")

    _activate_strength(actions, reader, emulator)
    _move(actions, reader, _directions("UUULUURULLLLL"), "3F Repel boundary")
    _settle_confirm(actions, reader, 4)
    _use_bag_item(actions, reader, emulator, DEFAULT_LAVENDER_TIMING, ItemId.MAX_REPEL)
    vr3_route = (
        ("left",) * 11
        + _directions("ULD")
        + _directions("RD")
        + ("left",) * 4
        + _directions("UL")
        + ("down",) * 3
        + _directions("LDR")
    )
    _move(actions, reader, vr3_route, "Victory Road 3F switch")
    vr3_switch = _event(reader.read(), EventFlag.VICTORY_ROAD_3F_BOULDER_ON_SWITCH_1)
    if not vr3_switch:
        raise VictoryRoadChapterError("Victory Road 3F switch did not set.")
    _move(actions, reader, VR3_SWITCH_TO_HOLE, "Victory Road hole boulder")
    _require(reader.read(), MapId.VICTORY_ROAD_3F, (21, 15), "3F hole boulder")
    _step(actions, reader, "right", "Drop 3F boulder")
    vr3_hole = _event(reader.read(), EventFlag.VICTORY_ROAD_3F_BOULDER_IN_HOLE)
    if not vr3_hole:
        raise VictoryRoadChapterError("Victory Road boulder did not enter the hole.")
    for _ in range(24):
        if reader.read().map_id == MapId.VICTORY_ROAD_2F:
            break
        _step(actions, reader, "right", "Follow boulder to 2F")
    _require(reader.read(), MapId.VICTORY_ROAD_2F, (22, 16), "Dropped-boulder 2F")
    _checkpoint(records, progress, emulator, reader.read(), "vr3_hole", "Dropped final boulder")

    _step(actions, reader, "down", "Final boulder flank")
    _activate_strength(actions, reader, emulator)
    _move(
        actions,
        reader,
        _directions("RRU") + ("left",) * 14,
        "Victory Road final switch",
    )
    vr2_switch2 = _event(reader.read(), EventFlag.VICTORY_ROAD_2F_BOULDER_ON_SWITCH_2)
    if not vr2_switch2:
        raise VictoryRoadChapterError("Victory Road final switch did not set.")
    _checkpoint(records, progress, emulator, reader.read(), "vr2_final", "Opened final barrier")
    _move(actions, reader, VR2_FINAL_TO_3F, "Southeast 3F ladder")
    _require(reader.read(), MapId.VICTORY_ROAD_3F, (27, 15), "Southeast 3F")
    _move(actions, reader, VR3_SOUTHEAST_TO_2F, "East 2F ladder")
    _require(reader.read(), MapId.VICTORY_ROAD_2F, (27, 7), "East 2F")
    _move(actions, reader, ("right",) * 3, "Victory Road exit")
    _require(reader.read(), MapId.ROUTE_23, (14, 32), "North Route 23")
    _move(actions, reader, ROUTE_23_TO_INDIGO, "Indigo Plateau approach")
    _require(reader.read(), MapId.INDIGO_PLATEAU, (10, 17), "Indigo Plateau")
    _move(actions, reader, ("up", "up"), "Indigo arrival script")
    _settle_confirm(actions, reader, 16)
    _move(actions, reader, ("up",) * 10, "Indigo lobby")
    _require(reader.read(), MapId.INDIGO_PLATEAU_LOBBY, (7, 11), "Indigo lobby")

    _move(actions, reader, ("up",) * 4, "Indigo nurse")
    _heal(actions, reader, emulator)
    _move(actions, reader, _directions("LLLLUUL"), "Indigo clerk")
    _require(reader.read(), MapId.INDIGO_PLATEAU_LOBBY, (2, 5), "Indigo clerk")
    _pulse(actions, MacroActionKind.MOVE, "left", 120)
    _sell_current_bag_item(actions, emulator, ItemId.TM38_FIRE_BLAST)
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    _sell_current_bag_item(actions, emulator, ItemId.NUGGET)
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    _sell_current_bag_item(actions, emulator, ItemId.TM28_DIG)
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    _sell_bag_stack(actions, emulator, ItemId.MAX_REPEL, 8)
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    _sell_bag_stack(actions, emulator, ItemId.POKE_BALL, 8)
    _pulse(actions, MacroActionKind.CANCEL)
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=2,
        item=ItemId.FULL_RESTORE,
        quantity=13,
        target_bag_quantity=13,
    )
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=4,
        item=ItemId.FULL_HEAL,
        quantity=3,
        target_bag_quantity=3,
    )
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=5,
        item=ItemId.REVIVE,
        quantity=2,
        target_bag_quantity=2,
    )
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    final = reader.read()
    final_bag = _bag(emulator)
    _checkpoint(records, progress, emulator, final, "indigo_ready", "Elite Four supplies ready")

    report = VictoryRoadChapterReport(
        records=tuple(records),
        final_raw=final,
        rival_turns=rival_turns,
        rival_party=rival_party,
        rival_potions_used=rival_potions_used,
        badge_checks=badge_checks,
        vr1_switch_set=vr1_switch,
        vr2_switch1_set=vr2_switch1,
        vr3_switch_set=vr3_switch,
        vr3_hole_set=vr3_hole,
        vr2_switch2_set=vr2_switch2,
        full_restores=final_bag.get(ItemId.FULL_RESTORE, 0),
        full_heals=final_bag.get(ItemId.FULL_HEAL, 0),
        revives=final_bag.get(ItemId.REVIVE, 0),
        hyper_potions=final_bag.get(ItemId.HYPER_POTION, 0),
        x_specials=final_bag.get(ItemId.X_SPECIAL, 0),
        max_repels=final_bag.get(ItemId.MAX_REPEL, 0),
        tm27_sold=ItemId.TM27_FISSURE not in final_bag,
        tm38_sold=ItemId.TM38_FIRE_BLAST not in final_bag,
        tm28_sold=ItemId.TM28_DIG not in final_bag,
        tm06_consumed=ItemId.TM06_TOXIC not in final_bag,
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        money_remaining=_money(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise VictoryRoadChapterError(f"Victory Road terminal evidence failed: {report!r}.")
    return report


def _defeat_route22_rival(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> tuple[tuple[RivalTurn, ...], int]:
    _pulse(actions, MacroActionKind.MOVE, "left", 240)
    for _ in range(40):
        if reader.read().battle_state == 2:
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise VictoryRoadChapterError("Route 22 rival battle did not start.")
    turns: list[RivalTurn] = []

    def policy(raw: RawGameState) -> int:
        species = raw.enemy_species_id or 0
        try:
            slot = (
                1
                if species == 0x9A and (raw.first_party_pp or (0, 0, 0, 0))[0] == 10
                else RIVAL_POLICY[species]
            )
        except KeyError as error:
            raise VictoryRoadChapterError(f"Unexpected Route 22 species {species:#04x}.") from error
        turns.append(
            RivalTurn(
                species,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                raw.first_party_hp or 0,
                raw.first_party_pp or (0, 0, 0, 0),
                slot,
            )
        )
        return slot

    class _HealBoundary(Exception):
        pass

    potions_used = 0
    recovery_reserve = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    last_recovery_turn = -1

    def health_aware_policy(raw: RawGameState) -> int:
        venusaur_threshold = 100 if next_sacrifice < 3 else 50
        heal_threshold = {
            0x95: 140,
            0x9A: venusaur_threshold,
        }.get(raw.enemy_species_id or 0, 140)
        if (
            (raw.first_party_hp or 0) < heal_threshold
            and len(turns) != last_recovery_turn
            and potions_used < recovery_reserve
        ):
            raise _HealBoundary
        return policy(raw)

    next_sacrifice = 1
    pivot_heals = 0
    while reader.read().battle_state:
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                health_aware_policy,
                expected_map=MapId.ROUTE_22,
                intent=BattleIntent(
                    "cross_victory_road",
                    battle_plan_id=RedBattlePlanId.VICTORY_ROAD_ROUTE_22_RIVAL,
                    resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
                ),
                timing=BattleRuntimeTiming(max_runtime_pulses=720),
                label="Route 22 rival",
            )
        except BattleRuntimeError as error:
            if not isinstance(error.__cause__, _HealBoundary):
                raise VictoryRoadChapterError(
                    "Route 22 rival battle runtime failed after recovery: "
                    f"party_hp={_party_hp(emulator)!r}, potions={potions_used}, "
                    f"pivot_heals={pivot_heals}, next_sacrifice={next_sacrifice}."
                ) from error
            if potions_used >= recovery_reserve:
                raise VictoryRoadChapterError(
                    "Route 22 rival exceeded the bounded recovery reserve."
                ) from error
            if reader.read().enemy_species_id == 0x9A and next_sacrifice < 3:
                potion_spent = _battle_sacrifice(
                    actions,
                    reader,
                    emulator,
                    next_sacrifice,
                    heal_lead=True,
                )
                next_sacrifice += 1
                pivot_heals += int(potion_spent)
            else:
                _battle_hyper_potion(reader, actions, emulator, DEFAULT_SILPH_TIMING)
                potion_spent = True
            potions_used += int(potion_spent)
            last_recovery_turn = len(turns)
    _settle_confirm(actions, reader, 30)
    return tuple(turns), potions_used


def _teach_toxic(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
    _select_bag_item(actions, emulator, ItemId.TM06_TOXIC, DEFAULT_LAVENDER_TIMING)
    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (0, 1) and _menu_cursor_active(emulator):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise VictoryRoadChapterError("TM06 did not reach party selection.")
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
        raise VictoryRoadChapterError("TM06 did not reach move deletion.")
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        raw = reader.read()
        if raw.first_party_moves == (0x5C, 0x46, 0x3A, 0x39) and ItemId.TM06_TOXIC not in _bag(
            emulator
        ):
            _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raw = reader.read()
    raise VictoryRoadChapterError(
        "TM06 did not replace the expendable opening move: "
        f"moves={raw.first_party_moves!r}, pp={raw.first_party_pp!r}, "
        f"tm_present={ItemId.TM06_TOXIC in _bag(emulator)}."
    )


def _acquire_and_teach_submission(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    _field_fly(actions, reader, emulator, ("down",) * 4, MapId.CELADON_CITY)
    _move(actions, reader, CITY_TO_MART, "Celadon Mart entry")
    _require(reader.read(), MapId.CELADON_MART_1F, (16, 7), "Celadon Mart 1F")
    _move(actions, reader, MART_1F_TO_2F, "Celadon Mart 2F")
    _require(reader.read(), MapId.CELADON_MART_2F, (12, 2), "Celadon Mart 2F")
    _move(actions, reader, _directions("LLLDDDLLL"), "TM17 clerk")
    _require(reader.read(), MapId.CELADON_MART_2F, (6, 5), "TM17 clerk")
    _pulse(actions, MacroActionKind.MOVE, "up", 120)
    _pulse(actions, MacroActionKind.INTERACT)
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=8,
        item=ItemId.TM17_SUBMISSION,
        quantity=2,
        target_bag_quantity=2,
    )
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=7,
        item=ItemId.TM09_TAKE_DOWN,
        quantity=1,
        target_bag_quantity=1,
    )
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    _teach_submission(actions, reader, emulator)
    _pulse(actions, MacroActionKind.MOVE, "up", 120)
    _pulse(actions, MacroActionKind.INTERACT)
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=5,
        item=ItemId.TM01_MEGA_PUNCH,
        quantity=2,
        target_bag_quantity=2,
    )
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    _move(actions, reader, _directions("RRRUUURRRRRRRU"), "Celadon Mart 3F")
    _require(reader.read(), MapId.CELADON_MART_3F, (16, 2), "Celadon Mart 3F")
    _move(actions, reader, MART_3F_TO_4F, "Celadon Mart 4F")
    _require(reader.read(), MapId.CELADON_MART_4F, (12, 2), "Celadon Mart 4F")
    _move(actions, reader, MART_4F_TO_5F, "Celadon Mart 5F")
    _require(reader.read(), MapId.CELADON_MART_5F, (16, 2), "Celadon Mart 5F")
    _move(
        actions,
        reader,
        ("left",) * 8 + ("down",) * 4 + ("left",) * 3 + ("up",),
        "X Special clerk",
    )
    _pulse(actions, MacroActionKind.MOVE, "up", 120)
    _pulse(actions, MacroActionKind.INTERACT)
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=6,
        item=ItemId.X_SPECIAL,
        quantity=6,
        target_bag_quantity=6,
    )
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    _move(
        actions,
        reader,
        ("down",) + ("right",) * 3 + ("up",) * 4 + ("right",) * 8 + ("up",),
        "Celadon Mart 4F return",
    )
    _move(actions, reader, MART_4F_TO_3F, "Celadon Mart 3F return")
    _move(actions, reader, MART_3F_TO_2F, "Celadon Mart 2F return")
    _move(actions, reader, MART_2F_TO_1F, "Celadon Mart return")
    _require(reader.read(), MapId.CELADON_MART_1F, (12, 2), "Celadon Mart 1F return")
    _move(actions, reader, MART_TO_CITY, "Celadon Mart exit")
    _require(reader.read(), MapId.CELADON_CITY, (10, 14), "Celadon Mart exit")


def _teach_submission(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
    _select_bag_item(
        actions,
        emulator,
        ItemId.TM17_SUBMISSION,
        DEFAULT_LAVENDER_TIMING,
    )
    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (0, 1) and _menu_cursor_active(emulator):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise VictoryRoadChapterError("TM17 did not reach party selection.")
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
        raise VictoryRoadChapterError("TM17 did not reach move deletion.")
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        raw = reader.read()
        if (
            raw.first_party_moves == (0x42, 0x46, 0x3A, 0x39)
            and _bag(emulator).get(ItemId.TM17_SUBMISSION, 0) == 1
        ):
            _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise VictoryRoadChapterError("TM17 did not replace Toxic.")


def _archive_silph_scope(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    if _bag(emulator).get(ItemId.SILPH_SCOPE, 0) != 1:
        raise VictoryRoadChapterError("Late-game PC cleanup requires the spent Silph Scope.")
    _move(
        actions,
        reader,
        ("down",) + ("right",) * 10,
        "Saffron PC approach",
    )
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (13, 4), "Saffron PC approach")
    try:
        _deposit_pc_item(
            actions,
            reader,
            emulator,
            ItemId.SILPH_SCOPE,
            DEFAULT_SILPH_TIMING,
        )
    except SabrinaChapterError as error:
        raise VictoryRoadChapterError("Late-game PC cleanup failed.") from error
    if ItemId.SILPH_SCOPE in _bag(emulator):
        raise VictoryRoadChapterError("Late-game PC cleanup retained the Silph Scope.")
    _move(
        actions,
        reader,
        ("left",) * 10 + ("up",),
        "Saffron PC return",
    )
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 3), "Saffron PC return")


def _battle_sacrifice(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    party_index: int,
    *,
    heal_lead: bool,
    healing_item: ItemId = ItemId.HYPER_POTION,
) -> bool:
    if _party_hp(emulator)[party_index] <= 0:
        raise VictoryRoadChapterError("Route 22 pivot target had already fainted.")
    _select_battle_main_command(actions, reader, 2)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, party_index, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.CONFIRM)

    pivot_ready = False
    for pulse_index in range(24):
        if _party_hp(emulator)[party_index] == 0:
            break
        raw = reader.read()
        if (
            raw.battle_state == 2
            and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
        ):
            pivot_ready = True
            break
        _pulse(
            actions,
            MacroActionKind.CANCEL if pulse_index % 4 == 3 else MacroActionKind.CONFIRM,
        )

    potion_spent = False
    if heal_lead and pivot_ready:
        _select_battle_main_command(actions, reader, 1)
        _pulse(actions, MacroActionKind.CONFIRM)
        before = _bag(emulator).get(healing_item, 0)
        _select_bag_item(
            actions,
            emulator,
            healing_item,
            DEFAULT_LAVENDER_TIMING,
        )
        _pulse(actions, MacroActionKind.CONFIRM)
        _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
        _pulse(actions, MacroActionKind.CONFIRM)
        for _ in range(24):
            if _party_hp(emulator)[party_index] == 0:
                break
            raw = reader.read()
            if (
                raw.battle_state == 2
                and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
            ):
                break
            _pulse(actions, MacroActionKind.CONFIRM)
        if before - _bag(emulator).get(healing_item, 0) != 1:
            raise VictoryRoadChapterError("Route 22 pivot recovery did not spend one item.")
        potion_spent = True

    for pulse_index in range(64):
        if _party_hp(emulator)[party_index] == 0:
            break
        raw = reader.read()
        if raw.battle_state != 2:
            raise VictoryRoadChapterError("Route 22 pivot left its trainer battle.")
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.MAIN:
            _select_battle_main_command(actions, reader, 0)
            _pulse(actions, MacroActionKind.CONFIRM)
            _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
            _pulse(actions, MacroActionKind.CONFIRM)
        else:
            _pulse(
                actions,
                MacroActionKind.CANCEL if pulse_index % 4 == 3 else MacroActionKind.CONFIRM,
            )
    else:
        raise VictoryRoadChapterError(
            "Route 22 pivot did not absorb a bounded attack: "
            f"party_hp={_party_hp(emulator)!r}, "
            f"menu={reader.read_battle_menu_state(reader.read())!r}."
        )

    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) <= 2
            and _menu_cursor_active(emulator)
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise VictoryRoadChapterError(
            "Route 22 forced-switch party menu did not settle: "
            f"current={emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)}, "
            f"scroll={emulator.read_u8(RamAddress.LIST_SCROLL_OFFSET)}."
        )
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        raw = reader.read()
        if (
            raw.battle_state == 2
            and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
        ):
            return potion_spent
        _pulse(actions, MacroActionKind.CONFIRM)
    raise VictoryRoadChapterError(
        "Route 22 pivot did not restore Blastoise: "
        f"party_hp={_party_hp(emulator)!r}, "
        f"active={emulator.read_u8(RamAddress.PLAYER_MON_NUMBER)}, "
        f"cursor={emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)}, "
        f"menu={reader.read_battle_menu_state(reader.read())!r}."
    )


def _sell_bag_stack(
    actions: _CountingExecutor,
    emulator: EmulatorState,
    item: ItemId,
    quantity: int,
) -> None:
    if _bag(emulator).get(item, 0) != quantity:
        raise VictoryRoadChapterError(
            f"Expected {quantity} {item.name} items at the Indigo sale boundary."
        )
    _pulse(actions, MacroActionKind.INTERACT)
    _pulse(actions, MacroActionKind.MOVE, "down")
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        raise VictoryRoadChapterError("Indigo shop did not select SELL.")
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        if absolute < len(_bag(emulator)) and tuple(_bag(emulator))[absolute] == item:
            break
        _pulse(actions, MacroActionKind.MOVE, "down", 120)
    else:
        raise VictoryRoadChapterError(f"Indigo sell list could not select {item.name}.")
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(quantity + 2):
        if (
            emulator.read_u8(RamAddress.SHOP_SELECTED_ITEM) == item
            and emulator.read_u8(RamAddress.SHOP_QUANTITY) == quantity
        ):
            break
        _pulse(actions, MacroActionKind.MOVE, "up", 120)
    else:
        raise VictoryRoadChapterError(
            f"Indigo sale quantity selector missed {quantity} {item.name}."
        )
    for _ in range(24):
        if item not in _bag(emulator):
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise VictoryRoadChapterError(f"Indigo did not sell the {item.name} stack.")


def _select_battle_main_command(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    target: int,
) -> None:
    coordinates = {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)}
    for pulse_index in range(24):
        menu = reader.read_battle_menu_state(reader.read())
        if menu.phase is not BattleMenuPhase.MAIN:
            _pulse(
                actions,
                MacroActionKind.CANCEL if pulse_index % 4 == 3 else MacroActionKind.CONFIRM,
            )
            continue
        current = menu.selected_main_command
        if current == target:
            return
        if current not in coordinates:
            raise VictoryRoadChapterError("Route 22 battle command cursor was invalid.")
        x, y = coordinates[current]
        target_x, target_y = coordinates[target]
        direction = (
            "right"
            if x < target_x
            else "left"
            if x > target_x
            else "down"
            if y < target_y
            else "up"
        )
        _pulse(actions, MacroActionKind.MOVE, direction, 120)
    raise VictoryRoadChapterError("Route 22 battle command cursor did not settle.")


def _menu_cursor_active(emulator: EmulatorState) -> bool:
    address = emulator.read_u8(RamAddress.MENU_CURSOR_LOCATION)
    address |= emulator.read_u8(int(RamAddress.MENU_CURSOR_LOCATION) + 1) << 8
    tile_map = int(RamAddress.TILE_MAP)
    return tile_map <= address < tile_map + 360 and emulator.read_u8(address) == 0xED


def _field_fly(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    town_direction: str | Iterable[str],
    expected_map: MapId,
) -> None:
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    directions = (town_direction,) if isinstance(town_direction, str) else tuple(town_direction)
    for direction in directions:
        _pulse(actions, MacroActionKind.MOVE, direction, 120)
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    for _ in range(12):
        if reader.read().map_id == expected_map:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    else:
        raise VictoryRoadChapterError(f"Fly did not reach {expected_map.name}.")
    _settle_confirm(actions, reader, 12)


def _field_surf(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    _pulse(actions, MacroActionKind.MOVE, "up", 120)
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(10):
        raw = reader.read()
        if (raw.player_x, raw.player_y) == (10, 103):
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise VictoryRoadChapterError("Surf did not enter the Route 23 water.")


def _activate_strength(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(8):
        _pulse(actions, MacroActionKind.CONFIRM)
    if reader.read().battle_state:
        raise VictoryRoadChapterError("Strength activation entered battle.")


def _pass_badge_gate(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    trigger: Iterable[str],
    event: EventFlag,
) -> None:
    _move_with_wilds(actions, reader, emulator, run, trigger, event.name)
    for _ in range(16):
        raw = reader.read()
        if _event(raw, event) and reader.read_input_readiness().ready:
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise VictoryRoadChapterError(f"{event.name} did not settle.")


def _heal(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    for _ in range(9):
        _pulse(actions, MacroActionKind.CONFIRM)
    moves = reader.read().first_party_moves or ()
    expected_pp = (25, 15, 10, 15) if moves and moves[0] == 0x42 else (10, 15, 10, 15)
    if (
        _party_hp(emulator) != _party_max_hp(emulator)
        or _party_status(emulator) != (0, 0, 0)
        or reader.read().first_party_pp != expected_pp
    ):
        raise VictoryRoadChapterError("Pokémon Center did not restore the qualified party.")
    for _ in range(6):
        _pulse(actions, MacroActionKind.CANCEL)
    if not reader.read_input_readiness().ready:
        raise VictoryRoadChapterError("Pokémon Center dialogue did not close.")


def _move(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    route: Iterable[str],
    label: str,
) -> None:
    for index, direction in enumerate(tuple(route), 1):
        _step(actions, reader, direction, f"{label} step {index}")


def _move_with_wilds(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    route: Iterable[str],
    label: str,
) -> None:
    for index, direction in enumerate(tuple(route), 1):
        before = reader.read()
        start = (before.map_id, before.player_x, before.player_y)
        for _ in range(16):
            _pulse(actions, MacroActionKind.MOVE, direction, 240)
            after = reader.read()
            if after.battle_state == 2:
                raise VictoryRoadChapterError(
                    f"{label} step {index} entered an unexpected trainer battle."
                )
            if after.battle_state == 1:
                _flee(actions, reader, emulator, run, DEFAULT_CELADON_TIMING)
                after = reader.read()
            if (after.map_id, after.player_x, after.player_y) != start:
                break
        else:
            raise VictoryRoadChapterError(f"{label} step {index} remained blocked at {start}.")


def _pulse(
    actions: _CountingExecutor,
    kind: MacroActionKind,
    value: str | None = None,
    frames: int = DEFAULT_HIDEOUT_TIMING.wait_frames,
) -> None:
    actions.execute(MacroAction(kind, value))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _step(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    direction: str,
    label: str,
) -> None:
    before = reader.read()
    start = (before.map_id, before.player_x, before.player_y)
    for _ in range(16):
        _pulse(actions, MacroActionKind.MOVE, direction, 240)
        after = reader.read()
        if after.battle_state:
            raise VictoryRoadChapterError(f"{label} entered an unexpected battle.")
        if (after.map_id, after.player_x, after.player_y) != start:
            return
    raise VictoryRoadChapterError(f"{label} remained blocked at {start}.")


def _settle_confirm(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    limit: int,
) -> None:
    for _ in range(limit):
        if reader.read_input_readiness().ready:
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise VictoryRoadChapterError("Scripted input did not settle.")


def _event(raw: RawGameState, event: EventFlag) -> bool:
    index = int(event)
    return bool(raw.event_flags[index // 8] & (1 << (index % 8)))


def _encounter_party(turns: Iterable[RivalTurn]) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    for turn in turns:
        identity = (turn.species, turn.level)
        if not result or result[-1] != identity:
            result.append(identity)
    return tuple(result)


def _rival_moves_valid(turns: Iterable[RivalTurn]) -> bool:
    toxic_seen = False
    for turn in turns:
        if turn.species == 0x9A and turn.move_slot == 1 and not toxic_seen:
            toxic_seen = True
            continue
        if turn.move_slot != RIVAL_POLICY[turn.species]:
            return False
    return toxic_seen


def _checkpoint(
    records: list[VictoryRoadCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(VictoryRoadCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            VictoryRoadProgress(
                checkpoint_id,
                label,
                len(records),
                VICTORY_ROAD_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _require(
    raw: RawGameState,
    map_id: MapId,
    coordinate: tuple[int, int],
    label: str,
) -> None:
    if raw.map_id != map_id or (raw.player_x, raw.player_y) != coordinate:
        raise VictoryRoadChapterError(
            f"{label} expected map {int(map_id):#04x} at {coordinate}, got "
            f"{raw.map_id!r} at {(raw.player_x, raw.player_y)}."
        )
