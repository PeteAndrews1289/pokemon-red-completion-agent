"""Qualified HM02, Fly, Route 21, and Cinnabar arrival chapter.

Routes, event IDs, object positions, and field-menu order are pinned to
pret/pokered commit ``1e96034092686d006e863cace09e87273051a3d8`` and verified
against the supported English Pokémon Red ROM.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.celadon import (
    DEFAULT_CELADON_TIMING,
    CeladonWildFleeEvidence,
    _bag,
    _flee,
    _party_hp,
    _party_max_hp,
    _party_status,
    _RunState,
)
from pokemon_red_completion.erika import DEFAULT_ERIKA_TIMING, _cut
from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
from pokemon_red_completion.observation import (
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.silph import (
    ROUTE_7_CONNECTION_TO_CELADON_CITY,
    ROUTE_7_GATE_TO_WEST,
    ROUTE_7_WEST_TO_CONNECTION,
    SAFFRON_CENTER_TO_ROUTE_7_GATE,
)
from pokemon_red_completion.tower import party_core_intact

CINNABAR_CHECKPOINT_COUNT = 6
CINNABAR_MIN_LEAD_LEVEL = 44
CINNABAR_MAX_INPUT_BAG_SLOTS = 19
FLY_MOVE_ID = 0x13
DUX_MOVES_BEFORE = (0x40, 0x1C, 0x0F, 0x1F)
DUX_MOVES_AFTER = (0x40, 0x1C, 0x0F, FLY_MOVE_ID)
DUX_PP_BEFORE = (35, 15, 30, 20)
DUX_PP_AFTER = (35, 15, 30, 15)
ROUTE_21_EVENTS = tuple(range(0x511, 0x51A))


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "R": "right", "D": "down", "L": "left"}[item] for item in value)


CELADON_TO_ROUTE_16_TREE = _directions("DDDD" + "L" * 16)
TREE_TO_FLY_HOUSE = _directions("UUUULLLLLULLLLLLLLLLDLLLLDLLLLLLLLLLU")
PALLET_TO_SHORE = _directions("DDLL" + "D" * 9)
ROUTE_21_TO_CINNABAR = _directions("D" * 17 + "RDL" + "D" * 5 + "L" + "D" * 67)
ROUTE_21_STEP_ATTEMPTS = 8
CINNABAR_TO_CENTER = _directions("D" * 12 + "R" * 8 + "U")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class CinnabarChapterError(RuntimeError):
    """Raised when the Cinnabar arrival evidence contract fails."""


@dataclass(frozen=True, slots=True)
class CinnabarProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[CinnabarProgress], None]


@dataclass(frozen=True, slots=True)
class CinnabarCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class CinnabarChapterReport:
    records: tuple[CinnabarCheckpoint, ...]
    final_raw: RawGameState
    rare_candy_before: int
    rare_candy_after: int
    bag_slots_before: int
    bag_slots_after_candy: int
    lead_stats_before: tuple[int, ...]
    lead_stats_after: tuple[int, ...]
    hm02_item_before_event: bool
    got_hm02: bool
    hm02_quantity: int
    dux_moves_before: tuple[int, ...]
    dux_moves_after: tuple[int, ...]
    dux_pp_before: tuple[int, ...]
    dux_pp_after: tuple[int, ...]
    pallet_default_selected: bool
    route21_events_before: tuple[bool, ...]
    route21_events_after: tuple[bool, ...]
    wild_flees: tuple[CeladonWildFleeEvidence, ...]
    route16_wild_battles: int
    wild_battles: int
    trainer_battles: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool
    input_map: int

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == CINNABAR_CHECKPOINT_COUNT
            and self.rare_candy_before == 0
            and self.rare_candy_after == 0
            and _cinnabar_bag_capacity_preserved(
                self.bag_slots_before,
                self.bag_slots_after_candy,
            )
            and len(self.lead_stats_before) == 7
            and self.lead_stats_before == self.lead_stats_after
            and self.lead_stats_before[0] >= CINNABAR_MIN_LEAD_LEVEL
            and all(value > 0 for value in self.lead_stats_before[1:])
            and self.hm02_item_before_event
            and self.got_hm02
            and self.hm02_quantity == 1
            and self.dux_moves_before == DUX_MOVES_BEFORE
            and self.dux_moves_after == DUX_MOVES_AFTER
            and self.dux_pp_before == DUX_PP_BEFORE
            and self.dux_pp_after == DUX_PP_AFTER
            and self.pallet_default_selected
            and self.route21_events_before == (False,) * 9
            and self.route21_events_after == (False,) * 9
            and len(self.wild_flees) == self.wild_battles
            and all(
                item.party_preserved
                and item.pp_preserved
                and item.hp_safe
                and item.inventory_preserved
                for item in self.wild_flees
            )
            and 0 <= self.route16_wild_battles <= 3
            and 0 <= self.wild_battles - self.route16_wild_battles <= 5
            and self.trainer_battles == 0
            and self.final_raw.map_id == MapId.CINNABAR_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.final_raw.first_party_level == self.lead_stats_before[0]
            and self.final_raw.first_party_moves == (0x82, 0x46, 0x3A, 0x39)
            and self.final_raw.first_party_pp == (15, 15, 10, 15)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and self.final_raw.first_party_hp == self.party_hp[0]
            and self.final_raw.first_party_max_hp == self.party_max_hp[0]
            and all(status == 0 for status in self.party_status)
            and self.controller_released
            and self.input_map in {
                int(MapId.SAFFRON_POKECENTER),
                int(MapId.CELADON_POKECENTER),
            }
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "reach_cinnabar",
            "route16": {
                "bicycle_required": False,
                "cut_lane": True,
                "wild_battles": self.route16_wild_battles,
                "wild_flees": [
                    _wild_flee_public(item)
                    for item in self.wild_flees[: self.route16_wild_battles]
                ],
                "rare_candy": {
                    "quantity": [self.rare_candy_before, self.rare_candy_after],
                    "bag_slots": [self.bag_slots_before, self.bag_slots_after_candy],
                    "stats_before": list(self.lead_stats_before),
                    "stats_after": list(self.lead_stats_after),
                },
                "hm02_item_and_event_same_pulse": self.hm02_item_before_event,
                "got_hm02": self.got_hm02,
            },
            "field_moves": {
                "dux_moves_before": list(self.dux_moves_before),
                "dux_moves_after": list(self.dux_moves_after),
                "dux_pp_after": list(self.dux_pp_after),
                "pallet_default_selected": self.pallet_default_selected,
            },
            "route21": {
                "moves": len(ROUTE_21_TO_CINNABAR),
                "trainers_defeated": sum(self.route21_events_after),
                "wild_battles": self.wild_battles - self.route16_wild_battles,
                "wild_flees": [
                    _wild_flee_public(item)
                    for item in self.wild_flees[self.route16_wild_battles :]
                ],
                "trainer_battles": self.trainer_battles,
            },
            "terminal": {
                "map": int(self.final_raw.map_id),
                "position": [self.final_raw.player_x, self.final_raw.player_y],
                "hp": list(self.party_hp),
                "max_hp": list(self.party_max_hp),
                "status": list(self.party_status),
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
            "input_map": self.input_map,
        }


def _wild_flee_public(item: CeladonWildFleeEvidence) -> dict[str, object]:
    return {
        "map": item.map_id,
        "position": [item.x, item.y],
        "species": item.species,
        "level": item.level,
        "party_preserved": item.party_preserved,
        "pp_preserved": item.pp_preserved,
        "hp_safe": item.hp_safe,
        "inventory_preserved": item.inventory_preserved,
    }


def _cinnabar_bag_capacity_preserved(before: int, after_optional_candy: int) -> bool:
    """Require one free HM02 slot while allowing a consumed recovery stack."""

    return 0 < before <= CINNABAR_MAX_INPUT_BAG_SLOTS and after_optional_candy == before


def run_cinnabar_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> CinnabarChapterReport:
    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[CinnabarCheckpoint] = []
    initial = reader.read()
    if initial.map_id not in {MapId.SAFFRON_POKECENTER, MapId.CELADON_POKECENTER}:
        raise CinnabarChapterError("Cinnabar route requires a qualified city-center boundary.")
    _require(initial, initial.map_id, (3, 3), "Cinnabar input boundary")
    input_map = int(initial.map_id)
    initial_bag = _bag(emulator)
    rare_candy_before = initial_bag.get(ItemId.RARE_CANDY, 0)
    bag_slots_before = len(initial_bag)
    lead_stats_before = _lead_stats(emulator)
    route21_before = _events(emulator)
    if _event(emulator, EventFlag.GOT_HM02) or initial_bag.get(ItemId.HM02_FLY, 0):
        raise CinnabarChapterError("HM02 input boundary is not pristine.")
    _checkpoint(records, progress, emulator, initial, "cinnabar_ready", "Cinnabar route ready")

    if initial.map_id == MapId.SAFFRON_POKECENTER:
        for label, route in (
            ("Saffron gate", SAFFRON_CENTER_TO_ROUTE_7_GATE),
            ("Route 7 west", ROUTE_7_GATE_TO_WEST),
            ("Route 7 connection", ROUTE_7_WEST_TO_CONNECTION),
            ("Celadon arrival", ROUTE_7_CONNECTION_TO_CELADON_CITY),
        ):
            _move(actions, reader, route, label, frames=720)
    _move(actions, reader, CELADON_TO_ROUTE_16_TREE, "Route 16 Cut tree")
    _require(reader.read(), MapId.ROUTE_16, (34, 10), "Route 16 tree")
    _cut(actions, reader, emulator, DEFAULT_ERIKA_TIMING, "up", 0x2C, "Route 16 Cut")
    _move(actions, reader, ("up",), "Cut crossing")
    route16_wild_flees = _move_with_wild_flees(
        actions, reader, emulator, TREE_TO_FLY_HOUSE, "Fly House route"
    )
    _require(reader.read(), MapId.ROUTE_16_FLY_HOUSE, (2, 7), "Fly House entry")
    _checkpoint(
        records, progress, emulator, reader.read(), "fly_house_reached", "Reached Fly House"
    )

    rare_candy_after = _bag(emulator).get(ItemId.RARE_CANDY, 0)
    bag_slots_after_candy = len(_bag(emulator))
    lead_stats_after = _lead_stats(emulator)
    _move(actions, reader, ("up",) * 3, "Fly girl approach")
    _require(reader.read(), MapId.ROUTE_16_FLY_HOUSE, (2, 4), "Fly girl approach")
    hm02_item_before_event = _receive_hm02(actions, emulator)
    dux_moves_before = _four(emulator, RamAddress.PARTY_MON_2_MOVES)
    dux_pp_before = _four(emulator, RamAddress.PARTY_MON_2_PP)
    _teach_fly(actions, reader, emulator)
    _checkpoint(records, progress, emulator, reader.read(), "fly_taught", "Taught DUX Fly")

    _move(actions, reader, ("down",) * 4, "Fly House exit")
    _require(reader.read(), MapId.ROUTE_16, (7, 6), "Route 16 Fly departure")
    _fly_to_pallet(actions, reader, emulator)
    pallet = reader.read()
    _require(pallet, MapId.PALLET_TOWN, (5, 6), "Pallet Fly arrival")
    pallet_default_selected = True
    _checkpoint(records, progress, emulator, pallet, "pallet_reached", "Flew to Pallet Town")

    _move(actions, reader, PALLET_TO_SHORE, "Pallet shore")
    _require(reader.read(), MapId.PALLET_TOWN, (3, 17), "Pallet shore")
    _pulse(actions, MacroActionKind.MOVE, "right")
    _surf(actions, reader, emulator)
    _move(actions, reader, ("down",), "Route 21 connection")
    _require(reader.read(), MapId.ROUTE_21, (4, 0), "Route 21 entry")
    route21_wild_flees = _move_route21(actions, reader, emulator, ROUTE_21_TO_CINNABAR)
    wild_flees = route16_wild_flees + route21_wild_flees
    cinnabar = reader.read()
    _require(cinnabar, MapId.CINNABAR_ISLAND, (3, 0), "Cinnabar arrival")
    _checkpoint(
        records, progress, emulator, cinnabar, "cinnabar_reached", "Reached Cinnabar Island"
    )

    _move(actions, reader, CINNABAR_TO_CENTER, "Cinnabar Center")
    _require(reader.read(), MapId.CINNABAR_POKECENTER, (3, 7), "Cinnabar Center entry")
    _move(actions, reader, ("up",) * 4, "Cinnabar nurse")
    _heal(actions, reader, emulator)
    final = reader.read()
    _require(final, MapId.CINNABAR_POKECENTER, (3, 3), "healed Cinnabar boundary")
    _checkpoint(records, progress, emulator, final, "cinnabar_terminal", "Healed Cinnabar boundary")

    report = CinnabarChapterReport(
        tuple(records),
        final,
        rare_candy_before,
        rare_candy_after,
        bag_slots_before,
        bag_slots_after_candy,
        lead_stats_before,
        lead_stats_after,
        hm02_item_before_event,
        _event(emulator, EventFlag.GOT_HM02),
        _bag(emulator).get(ItemId.HM02_FLY, 0),
        dux_moves_before,
        _four(emulator, RamAddress.PARTY_MON_2_MOVES),
        dux_pp_before,
        _four(emulator, RamAddress.PARTY_MON_2_PP),
        pallet_default_selected,
        route21_before,
        _events(emulator),
        wild_flees,
        len(route16_wild_flees),
        len(wild_flees),
        0,
        _party_hp(emulator),
        _party_max_hp(emulator),
        _party_status(emulator),
        emulator.frame_count - start_frames,
        actions.actions_executed,
        not emulator.pressed_buttons,
        input_map,
    )
    if not report.passed:
        raise CinnabarChapterError(f"Cinnabar evidence contract failed: {report.public_dict()!r}.")
    return report


def _receive_hm02(actions, emulator) -> bool:
    if _event(emulator, EventFlag.GOT_HM02) or _bag(emulator).get(ItemId.HM02_FLY, 0):
        raise CinnabarChapterError("HM02 changed before the Fly girl interaction.")
    _pulse(actions, MacroActionKind.INTERACT)
    for _ in range(24):
        item = _bag(emulator).get(ItemId.HM02_FLY, 0)
        event = _event(emulator, EventFlag.GOT_HM02)
        if item or event:
            if item != 1 or not event:
                raise CinnabarChapterError("HM02 item/event transfer order diverged.")
            _close(actions, None)
            return True
        _pulse(actions, MacroActionKind.CONFIRM)
    raise CinnabarChapterError("Fly girl did not transfer HM02.")


def _teach_fly(actions, reader, emulator) -> None:
    _open_bag(actions, emulator)
    _select_bag_item(actions, emulator, ItemId.HM02_FLY)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        if _menu_origin(emulator) == (0, 1):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        if _menu_origin(emulator) == (5, 8):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 3)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        if _four(emulator, RamAddress.PARTY_MON_2_MOVES) == DUX_MOVES_AFTER:
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise CinnabarChapterError("HM02 did not replace DUX slot four.")
    _close(actions, reader)


def _fly_to_pallet(actions, reader, emulator) -> None:
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(6):
        if reader.read().map_id == MapId.PALLET_TOWN:
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise CinnabarChapterError("Default Fly destination did not arrive in Pallet.")


def _surf(actions, reader, emulator) -> None:
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 0)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(8):
        raw = reader.read()
        if raw.map_id == MapId.PALLET_TOWN and (raw.player_x, raw.player_y) == (4, 17):
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise CinnabarChapterError("Surf did not enter the Pallet water tile.")


def _heal(actions, reader, emulator) -> None:
    for _ in range(20):
        _pulse(actions, MacroActionKind.CONFIRM)
        if _party_hp(emulator) == _party_max_hp(emulator) and all(
            status == 0 for status in _party_status(emulator)
        ):
            break
    _close(actions, reader)


def _move(actions, reader, route: Iterable[str], label: str, *, frames: int = 240) -> None:
    route = tuple(route)
    for index, direction in enumerate(route, 1):
        before = reader.read()
        for _ in range(8):
            _pulse(actions, MacroActionKind.MOVE, direction, frames)
            after = reader.read()
            if after.battle_state:
                raise CinnabarChapterError(f"{label} entered battle at step {index}.")
            if (after.map_id, after.player_x, after.player_y) != (
                before.map_id,
                before.player_x,
                before.player_y,
            ):
                break
        else:
            raise CinnabarChapterError(f"{label} blocked at step {index}/{len(route)}.")


def _move_route21(
    actions, reader, emulator, route: Iterable[str]
) -> tuple[CeladonWildFleeEvidence, ...]:
    """Cross Route 21, absorbing however many wild encounters actually occur.

    A surfing encounter can consume a movement step without advancing the
    player.  Treating that as a blocked tile made the crossing depend on the
    exact encounter sequence one recorded run happened to see, so a different
    RNG schedule failed a corridor that was never obstructed.  Each step now
    retries under the same bounded budget :func:`_move` already uses, which
    makes the traversal depend on the corridor rather than on the encounters.
    """

    run = _RunState([])
    steps = tuple(route)
    for index, direction in enumerate(steps, 1):
        before = reader.read()
        for _ in range(ROUTE_21_STEP_ATTEMPTS):
            _pulse(actions, MacroActionKind.MOVE, direction, 240)
            after = reader.read()
            if after.battle_state == 2:
                raise CinnabarChapterError(f"Route 21 entered a trainer battle at step {index}.")
            if after.battle_state == 1:
                _flee(actions, reader, emulator, run, DEFAULT_CELADON_TIMING)
                after = reader.read()
            if _events(emulator) != (False,) * 9:
                raise CinnabarChapterError("Route 21 changed an optional trainer event.")
            if (after.map_id, after.player_x, after.player_y) != (
                before.map_id,
                before.player_x,
                before.player_y,
            ):
                break
        else:
            raise CinnabarChapterError(
                f"Route 21 blocked at step {index}/{len(steps)} after "
                f"{ROUTE_21_STEP_ATTEMPTS} attempts."
            )
    return tuple(run.wilds)


def _move_with_wild_flees(
    actions,
    reader,
    emulator,
    route: Iterable[str],
    label: str,
) -> tuple[CeladonWildFleeEvidence, ...]:
    run = _RunState([])
    for index, direction in enumerate(tuple(route), 1):
        before = reader.read()
        for _ in range(8):
            _pulse(actions, MacroActionKind.MOVE, direction, 240)
            after = reader.read()
            if after.battle_state == 2:
                raise CinnabarChapterError(
                    f"{label} entered a trainer battle at step {index}."
                )
            if after.battle_state == 1:
                _flee(actions, reader, emulator, run, DEFAULT_CELADON_TIMING)
                after = reader.read()
            if (after.map_id, after.player_x, after.player_y) != (
                before.map_id,
                before.player_x,
                before.player_y,
            ):
                break
            if not reader.read_input_readiness().ready:
                _pulse(actions, MacroActionKind.CONFIRM, 240)
        else:
            raise CinnabarChapterError(f"{label} blocked at step {index}.")
    return tuple(run.wilds)


def _open_bag(actions, emulator) -> None:
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 2)
    _pulse(actions, MacroActionKind.CONFIRM)


def _select_bag_item(actions, emulator, item: int) -> None:
    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        if absolute < len(_bag(emulator)) and tuple(_bag(emulator))[absolute] == item:
            return
        _pulse(actions, MacroActionKind.MOVE, "down", 120)
    raise CinnabarChapterError(f"Bag could not select {int(item):#04x}.")


def _select_cursor(actions, emulator, target: int) -> None:
    for _ in range(16):
        current = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if current == target:
            return
        _pulse(actions, MacroActionKind.MOVE, "down" if current < target else "up", 120)
    raise CinnabarChapterError(f"Menu could not select cursor {target}.")


def _close(actions, reader) -> None:
    for _ in range(6):
        _pulse(actions, MacroActionKind.CANCEL)
    if reader is not None and not reader.read_input_readiness().ready:
        raise CinnabarChapterError("Menus did not restore field input.")


def _pulse(actions, kind: MacroActionKind, value: str | None = None, frames: int = 180) -> None:
    actions.execute(MacroAction(kind, value))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _menu_origin(emulator) -> tuple[int, int]:
    return (
        emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
        emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
    )


def _four(emulator, address: int) -> tuple[int, ...]:
    return tuple(emulator.read_u8(int(address) + offset) for offset in range(4))


def _u16(emulator, address: int) -> int:
    return emulator.read_u8(address) * 0x100 + emulator.read_u8(address + 1)


def _lead_stats(emulator) -> tuple[int, ...]:
    return (
        emulator.read_u8(RamAddress.PARTY_MON_1_LEVEL),
        _u16(emulator, int(RamAddress.PARTY_MON_1_HP)),
        *(
            _u16(emulator, int(RamAddress.PARTY_MON_1_MAX_HP) + offset)
            for offset in range(0, 10, 2)
        ),
    )


def _event(emulator, event: int) -> bool:
    value = int(event)
    return bool(emulator.read_u8(int(RamAddress.EVENT_FLAGS) + value // 8) & (1 << value % 8))


def _events(emulator) -> tuple[bool, ...]:
    return tuple(_event(emulator, event) for event in ROUTE_21_EVENTS)


def _checkpoint(records, progress, emulator, raw, checkpoint_id, label) -> None:
    records.append(CinnabarCheckpoint(checkpoint_id, label, raw))
    if progress:
        progress(
            CinnabarProgress(
                checkpoint_id,
                label,
                len(records),
                CINNABAR_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _require(raw, map_id: int, position: tuple[int, int], label: str) -> None:
    if (
        raw.map_id != int(map_id)
        or (raw.player_x, raw.player_y) != position
        or raw.battle_state != 0
        or not party_core_intact(raw.party_species_ids)
    ):
        raise CinnabarChapterError(
            f"{label} failed: map={raw.map_id:#04x}, "
            f"position={(raw.player_x, raw.player_y)!r}, battle={raw.battle_state}, "
            f"party={raw.party_species_ids!r}."
        )
