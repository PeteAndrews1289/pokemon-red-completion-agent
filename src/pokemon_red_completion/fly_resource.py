"""Qualified HM02/Fly resource lesson for alternate-order construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.celadon import _bag, _party_hp, _party_max_hp, _party_status
from pokemon_red_completion.cinnabar import (
    DUX_MOVES_AFTER,
    DUX_MOVES_BEFORE,
    DUX_PP_AFTER,
    DUX_PP_BEFORE,
    TREE_TO_FLY_HOUSE,
    _close,
    _four,
    _move,
    _move_with_wild_flees,
    _receive_hm02,
    _select_cursor,
    _teach_fly,
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
from pokemon_red_completion.tower import party_core_intact

FLY_RESOURCE_CHECKPOINT_COUNT = 5
FLY_ATTEMPT_LIMIT = 10
SOURCE_CITY_BOUNDARY = (49, 11)
CELADON_CENTER_DOOR = (41, 9)
CINNABAR_CENTER_TO_OUTDOORS = ("down",) * 5
CELADON_CENTER_TO_OUTDOORS = ("down",) * 5
CENTER_TO_ROUTE_16_TREE = (
    ("down",) * 8
    + ("left",) * 22
    + ("down", "left")
    + ("down",) * 4
    + ("left",) * 24
)


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class FlyResourceError(RuntimeError):
    """Raised when the independent HM02 lesson loses semantic evidence."""


@dataclass(frozen=True, slots=True)
class FlyResourceCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class FlyResourceReport:
    records: tuple[FlyResourceCheckpoint, ...]
    initial_raw: RawGameState
    final_raw: RawGameState
    initial_bag: tuple[tuple[int, int], ...]
    final_bag: tuple[tuple[int, int], ...]
    hm02_item_before_event: bool
    got_hm02: bool
    dux_moves_before: tuple[int, ...]
    dux_moves_after: tuple[int, ...]
    dux_pp_before: tuple[int, ...]
    dux_pp_after: tuple[int, ...]
    wild_battles: int
    fly_landings: tuple[tuple[int, int], ...]
    party_hp_before: tuple[int, ...]
    party_hp_after: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        expected_bag = tuple(sorted((*self.initial_bag, (int(ItemId.HM02_FLY), 1))))
        return (
            len(self.records) == FLY_RESOURCE_CHECKPOINT_COUNT
            and self.final_bag == expected_bag
            and self.hm02_item_before_event
            and self.got_hm02
            and self.dux_moves_before == DUX_MOVES_BEFORE
            and self.dux_moves_after == DUX_MOVES_AFTER
            and self.dux_pp_before == DUX_PP_BEFORE
            and self.dux_pp_after == DUX_PP_AFTER
            and 0 <= self.wild_battles <= 3
            and bool(self.fly_landings)
            and self.fly_landings[-1][0] == int(MapId.CELADON_CITY)
            and len(self.fly_landings) <= FLY_ATTEMPT_LIMIT
            and self.initial_raw.party_species_ids == self.final_raw.party_species_ids
            and self.initial_raw.first_party_moves == self.final_raw.first_party_moves
            and self.party_hp_before == self.party_hp_after
            and all(
                0 < hp <= maximum
                for hp, maximum in zip(self.party_hp_after, self.party_max_hp, strict=True)
            )
            and all(status == 0 for status in self.party_status)
            and self.final_raw.map_id == MapId.CELADON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.battle_state == 0
            and party_core_intact(self.final_raw.party_species_ids)
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "resource": "fly",
            "objective_added": False,
            "hm02": {
                "item_and_event_same_pulse": self.hm02_item_before_event,
                "event": self.got_hm02,
                "reusable_item_retained": (int(ItemId.HM02_FLY), 1) in self.final_bag,
            },
            "dux": {
                "moves_before": list(self.dux_moves_before),
                "moves_after": list(self.dux_moves_after),
                "pp_after": list(self.dux_pp_after),
            },
            "route16_wild_battles": self.wild_battles,
            "fly_attempts": len(self.fly_landings),
            "fly_landing_maps": [map_id for map_id, _ in self.fly_landings],
            "returned_to_celadon_center": True,
            "bag_before": [list(entry) for entry in self.initial_bag],
            "bag_after": [list(entry) for entry in self.final_bag],
            "party_hp_before": list(self.party_hp_before),
            "party_hp_after": list(self.party_hp_after),
            "party_max_hp": list(self.party_max_hp),
            "party_status": list(self.party_status),
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


@dataclass(frozen=True, slots=True)
class FlyRelocationReport:
    """Evidence for a story-neutral Cinnabar-to-Celadon Fly relocation."""

    initial_raw: RawGameState
    final_raw: RawGameState
    initial_bag: tuple[tuple[int, int], ...]
    final_bag: tuple[tuple[int, int], ...]
    dux_moves: tuple[int, ...]
    dux_pp_before: tuple[int, ...]
    dux_pp_after: tuple[int, ...]
    fly_landings: tuple[tuple[int, int], ...]
    party_hp_before: tuple[int, ...]
    party_hp_after: tuple[int, ...]
    party_max_hp_before: tuple[int, ...]
    party_max_hp_after: tuple[int, ...]
    party_status_before: tuple[int, ...]
    party_status_after: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            self.initial_raw.map_id == MapId.CINNABAR_POKECENTER
            and (self.initial_raw.player_x, self.initial_raw.player_y) == (3, 3)
            and self.initial_raw.battle_state == 0
            and self.final_raw.map_id == MapId.CELADON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.battle_state == 0
            and self.initial_raw.party_species_ids == self.final_raw.party_species_ids
            and self.initial_raw.first_party_moves == self.final_raw.first_party_moves
            and self.initial_raw.first_party_pp == self.final_raw.first_party_pp
            and self.initial_bag == self.final_bag
            and (int(ItemId.HM02_FLY), 1) in self.final_bag
            and self.dux_moves == DUX_MOVES_AFTER
            and self.dux_pp_before == DUX_PP_AFTER
            and self.dux_pp_after == DUX_PP_AFTER
            and bool(self.fly_landings)
            and self.fly_landings[-1][0] == int(MapId.CELADON_CITY)
            and len(self.fly_landings) <= FLY_ATTEMPT_LIMIT
            and self.party_hp_before == self.party_hp_after
            and self.party_max_hp_before == self.party_max_hp_after
            and self.party_status_before == self.party_status_after
            and all(
                0 < hp <= maximum
                for hp, maximum in zip(
                    self.party_hp_after,
                    self.party_max_hp_after,
                    strict=True,
                )
            )
            and all(status == 0 for status in self.party_status_after)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "relocation": "cinnabar_to_celadon_by_fly",
            "objective_added": False,
            "fly_attempts": len(self.fly_landings),
            "fly_landing_maps": [map_id for map_id, _ in self.fly_landings],
            "party_preserved": (
                self.initial_raw.party_species_ids == self.final_raw.party_species_ids
                and self.party_hp_before == self.party_hp_after
                and self.party_max_hp_before == self.party_max_hp_after
                and self.party_status_before == self.party_status_after
            ),
            "inventory_preserved": self.initial_bag == self.final_bag,
            "returned_to_celadon_center": (
                self.final_raw.map_id == MapId.CELADON_POKECENTER
                and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            ),
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


@dataclass(frozen=True, slots=True)
class CinnabarFlyArrivalReport:
    """Evidence for a story-neutral Celadon-to-Cinnabar Fly relocation."""

    initial_raw: RawGameState
    final_raw: RawGameState
    initial_bag: tuple[tuple[int, int], ...]
    final_bag: tuple[tuple[int, int], ...]
    dux_moves: tuple[int, ...]
    dux_pp_before: tuple[int, ...]
    dux_pp_after: tuple[int, ...]
    fly_landings: tuple[tuple[int, int], ...]
    party_hp_before: tuple[int, ...]
    party_hp_after: tuple[int, ...]
    party_max_hp_before: tuple[int, ...]
    party_max_hp_after: tuple[int, ...]
    party_status_before: tuple[int, ...]
    party_status_after: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            (self.initial_raw.map_id, self.initial_raw.player_x, self.initial_raw.player_y)
            in {
                (MapId.CELADON_POKECENTER, 3, 3),
                (MapId.CELADON_CITY, *SOURCE_CITY_BOUNDARY),
            }
            and self.initial_raw.battle_state == 0
            and self.final_raw.map_id == MapId.CINNABAR_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.battle_state == 0
            and self.initial_raw.party_species_ids == self.final_raw.party_species_ids
            and self.initial_raw.first_party_moves == self.final_raw.first_party_moves
            and self.initial_raw.first_party_pp == self.final_raw.first_party_pp
            and self.initial_bag == self.final_bag
            and (int(ItemId.HM02_FLY), 1) in self.final_bag
            and self.dux_moves == DUX_MOVES_AFTER
            and self.dux_pp_before == DUX_PP_AFTER
            and self.dux_pp_after == DUX_PP_AFTER
            and bool(self.fly_landings)
            and self.fly_landings[-1][0] == int(MapId.CINNABAR_ISLAND)
            and len(self.fly_landings) <= FLY_ATTEMPT_LIMIT
            and self.party_hp_before == self.party_hp_after
            and self.party_max_hp_before == self.party_max_hp_after
            and self.party_status_before == self.party_status_after
            and all(
                0 < hp <= maximum
                for hp, maximum in zip(
                    self.party_hp_after,
                    self.party_max_hp_after,
                    strict=True,
                )
            )
            and all(status == 0 for status in self.party_status_after)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.controller_released
        )


@dataclass(frozen=True, slots=True)
class FuchsiaFlyArrivalReport:
    """Evidence for a story-neutral Cinnabar-to-Fuchsia Fly relocation."""

    initial_raw: RawGameState
    final_raw: RawGameState
    initial_bag: tuple[tuple[int, int], ...]
    final_bag: tuple[tuple[int, int], ...]
    dux_moves: tuple[int, ...]
    dux_pp_before: tuple[int, ...]
    dux_pp_after: tuple[int, ...]
    fly_landings: tuple[tuple[int, int], ...]
    party_hp_before: tuple[int, ...]
    party_hp_after: tuple[int, ...]
    party_max_hp_before: tuple[int, ...]
    party_max_hp_after: tuple[int, ...]
    party_status_before: tuple[int, ...]
    party_status_after: tuple[int, ...]
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            self.initial_raw.map_id == MapId.CINNABAR_POKECENTER
            and (self.initial_raw.player_x, self.initial_raw.player_y) == (3, 3)
            and self.initial_raw.battle_state == 0
            and self.final_raw.map_id == MapId.FUCHSIA_CITY
            and self.final_raw.battle_state == 0
            and self.initial_raw.party_species_ids == self.final_raw.party_species_ids
            and self.initial_raw.first_party_moves == self.final_raw.first_party_moves
            and self.initial_raw.first_party_pp == self.final_raw.first_party_pp
            and self.initial_bag == self.final_bag
            and (int(ItemId.HM02_FLY), 1) in self.final_bag
            and self.dux_moves == DUX_MOVES_AFTER
            and self.dux_pp_before == DUX_PP_AFTER
            and self.dux_pp_after == DUX_PP_AFTER
            and bool(self.fly_landings)
            and self.fly_landings[-1][0] == int(MapId.FUCHSIA_CITY)
            and len(self.fly_landings) <= FLY_ATTEMPT_LIMIT
            and self.party_hp_before == self.party_hp_after
            and self.party_max_hp_before == self.party_max_hp_after
            and self.party_status_before == self.party_status_after
            and all(status == 0 for status in self.party_status_after)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.controller_released
        )


def run_fly_resource_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
) -> FlyResourceReport:
    """Acquire Fly in Celadon and return to the Center without story progress."""

    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[FlyResourceCheckpoint] = []
    initial = reader.read()
    initial_bag = _bag_tuple(emulator)
    hp_before = _party_hp(emulator)
    if (
        initial.map_id not in {MapId.CELADON_CITY, MapId.CELADON_POKECENTER}
        or initial.battle_state != 0
        or _event(emulator, EventFlag.GOT_HM02)
        or ItemId.HM02_FLY in _bag(emulator)
        or _four(emulator, RamAddress.PARTY_MON_2_MOVES) != DUX_MOVES_BEFORE
        or _four(emulator, RamAddress.PARTY_MON_2_PP) != DUX_PP_BEFORE
        or not party_core_intact(initial.party_species_ids)
    ):
        raise FlyResourceError("Fly resource input boundary is not pristine.")
    _checkpoint(records, initial, "fly_ready", "Celadon Fly resource ready")

    _normalize_celadon_center(actions, reader)
    _move(actions, reader, CENTER_TO_ROUTE_16_TREE, "Route 16 Cut tree")
    _require(reader.read(), MapId.ROUTE_16, (34, 10), "Route 16 tree")
    _cut(actions, reader, emulator, DEFAULT_ERIKA_TIMING, "up", 0x2C, "Route 16 Cut")
    _move(actions, reader, ("up",), "Cut crossing")
    wild_flees = _move_with_wild_flees(
        actions,
        reader,
        emulator,
        TREE_TO_FLY_HOUSE,
        "Fly House route",
    )
    _require(reader.read(), MapId.ROUTE_16_FLY_HOUSE, (2, 7), "Fly House entry")
    _checkpoint(records, reader.read(), "fly_house", "Reached Fly House")

    _move(actions, reader, ("up",) * 3, "Fly girl approach")
    _require(reader.read(), MapId.ROUTE_16_FLY_HOUSE, (2, 4), "Fly girl approach")
    hm02_item_before_event = _receive_hm02(actions, emulator)
    dux_moves_before = _four(emulator, RamAddress.PARTY_MON_2_MOVES)
    dux_pp_before = _four(emulator, RamAddress.PARTY_MON_2_PP)
    _teach_fly(actions, reader, emulator)
    _checkpoint(records, reader.read(), "fly_taught", "Taught DUX Fly")

    _move(actions, reader, ("down",) * 4, "Fly House exit")
    _require(reader.read(), MapId.ROUTE_16, (7, 6), "Route 16 Fly departure")
    landings = _fly_to_celadon(actions, reader, emulator)
    _checkpoint(records, reader.read(), "celadon_landed", "Flew back to Celadon")
    _normalize_celadon_center(actions, reader)
    final = reader.read()
    _checkpoint(records, final, "fly_stable", "Stable Celadon Fly boundary")

    report = FlyResourceReport(
        records=tuple(records),
        initial_raw=initial,
        final_raw=final,
        initial_bag=initial_bag,
        final_bag=_bag_tuple(emulator),
        hm02_item_before_event=hm02_item_before_event,
        got_hm02=_event(emulator, EventFlag.GOT_HM02),
        dux_moves_before=dux_moves_before,
        dux_moves_after=_four(emulator, RamAddress.PARTY_MON_2_MOVES),
        dux_pp_before=dux_pp_before,
        dux_pp_after=_four(emulator, RamAddress.PARTY_MON_2_PP),
        wild_battles=len(wild_flees),
        fly_landings=landings,
        party_hp_before=hp_before,
        party_hp_after=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise FlyResourceError(f"Fly resource evidence failed: {report.public_dict()!r}.")
    return report


def relocate_cinnabar_to_celadon_by_fly(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
) -> FlyRelocationReport:
    """Return an authenticated Cinnabar boundary to Celadon without story effects."""

    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    initial = reader.read()
    initial_bag = _bag_tuple(emulator)
    hp_before = _party_hp(emulator)
    max_hp_before = _party_max_hp(emulator)
    status_before = _party_status(emulator)
    dux_moves = _four(emulator, RamAddress.PARTY_MON_2_MOVES)
    dux_pp_before = _four(emulator, RamAddress.PARTY_MON_2_PP)
    if (
        initial.map_id != MapId.CINNABAR_POKECENTER
        or (initial.player_x, initial.player_y) != (3, 3)
        or initial.battle_state != 0
        or not _event(emulator, EventFlag.GOT_HM02)
        or initial_bag.count((int(ItemId.HM02_FLY), 1)) != 1
        or dux_moves != DUX_MOVES_AFTER
        or dux_pp_before != DUX_PP_AFTER
        or not party_core_intact(initial.party_species_ids)
    ):
        raise FlyResourceError("Cinnabar Fly relocation input is not qualified.")

    _move(actions, reader, CINNABAR_CENTER_TO_OUTDOORS, "Cinnabar Fly departure")
    outdoors = reader.read()
    if outdoors.map_id != MapId.CINNABAR_ISLAND or outdoors.battle_state != 0:
        raise FlyResourceError("Cinnabar Center exit did not reach the island field.")
    landings = _fly_to_celadon(actions, reader, emulator)
    _normalize_celadon_center(actions, reader)
    final = reader.read()

    report = FlyRelocationReport(
        initial_raw=initial,
        final_raw=final,
        initial_bag=initial_bag,
        final_bag=_bag_tuple(emulator),
        dux_moves=dux_moves,
        dux_pp_before=dux_pp_before,
        dux_pp_after=_four(emulator, RamAddress.PARTY_MON_2_PP),
        fly_landings=landings,
        party_hp_before=hp_before,
        party_hp_after=_party_hp(emulator),
        party_max_hp_before=max_hp_before,
        party_max_hp_after=_party_max_hp(emulator),
        party_status_before=status_before,
        party_status_after=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise FlyResourceError(
            f"Cinnabar Fly relocation evidence failed: {report.public_dict()!r}."
        )
    return report


def relocate_celadon_to_cinnabar_by_fly(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
) -> CinnabarFlyArrivalReport:
    """Reach an unlocked Cinnabar boundary from Celadon without story effects."""

    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    initial = reader.read()
    initial_bag = _bag_tuple(emulator)
    hp_before = _party_hp(emulator)
    max_hp_before = _party_max_hp(emulator)
    status_before = _party_status(emulator)
    dux_moves = _four(emulator, RamAddress.PARTY_MON_2_MOVES)
    dux_pp_before = _four(emulator, RamAddress.PARTY_MON_2_PP)
    if (
        (initial.map_id, initial.player_x, initial.player_y)
        not in {
            (MapId.CELADON_POKECENTER, 3, 3),
            (MapId.CELADON_CITY, *SOURCE_CITY_BOUNDARY),
        }
        or initial.battle_state != 0
        or not _event(emulator, EventFlag.GOT_HM02)
        or initial_bag.count((int(ItemId.HM02_FLY), 1)) != 1
        or dux_moves != DUX_MOVES_AFTER
        or dux_pp_before != DUX_PP_AFTER
        or not party_core_intact(initial.party_species_ids)
    ):
        raise FlyResourceError("Celadon Fly relocation input is not qualified.")

    if initial.map_id == MapId.CELADON_POKECENTER:
        _move(actions, reader, CELADON_CENTER_TO_OUTDOORS, "Celadon Fly departure")
    outdoors = reader.read()
    if outdoors.map_id != MapId.CELADON_CITY or outdoors.battle_state != 0:
        raise FlyResourceError("Celadon Center exit did not reach the city field.")
    landings = _fly_to_destination(
        actions,
        reader,
        emulator,
        MapId.CINNABAR_ISLAND,
    )
    raw = reader.read()
    if raw.map_id != MapId.CINNABAR_ISLAND or (raw.player_x, raw.player_y) != (11, 12):
        raise FlyResourceError("Fly did not reach the measured Cinnabar landing.")
    _move(actions, reader, ("up",) * 5, "Cinnabar Center normalization")
    final = reader.read()

    report = CinnabarFlyArrivalReport(
        initial_raw=initial,
        final_raw=final,
        initial_bag=initial_bag,
        final_bag=_bag_tuple(emulator),
        dux_moves=dux_moves,
        dux_pp_before=dux_pp_before,
        dux_pp_after=_four(emulator, RamAddress.PARTY_MON_2_PP),
        fly_landings=landings,
        party_hp_before=hp_before,
        party_hp_after=_party_hp(emulator),
        party_max_hp_before=max_hp_before,
        party_max_hp_after=_party_max_hp(emulator),
        party_status_before=status_before,
        party_status_after=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise FlyResourceError("Cinnabar Fly arrival evidence failed.")
    return report


def relocate_cinnabar_to_fuchsia_by_fly(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
) -> FuchsiaFlyArrivalReport:
    """Return an authenticated Cinnabar boundary to Fuchsia without story effects."""

    actions = CountingExecutor(executor)
    initial = reader.read()
    initial_bag = _bag_tuple(emulator)
    hp_before = _party_hp(emulator)
    max_hp_before = _party_max_hp(emulator)
    status_before = _party_status(emulator)
    dux_moves = _four(emulator, RamAddress.PARTY_MON_2_MOVES)
    dux_pp_before = _four(emulator, RamAddress.PARTY_MON_2_PP)
    if (
        initial.map_id != MapId.CINNABAR_POKECENTER
        or (initial.player_x, initial.player_y) != (3, 3)
        or initial.battle_state != 0
        or not _event(emulator, EventFlag.GOT_HM02)
        or initial_bag.count((int(ItemId.HM02_FLY), 1)) != 1
        or dux_moves != DUX_MOVES_AFTER
        or dux_pp_before != DUX_PP_AFTER
        or not party_core_intact(initial.party_species_ids)
    ):
        raise FlyResourceError("Cinnabar-to-Fuchsia Fly input is not qualified.")

    _move(actions, reader, CINNABAR_CENTER_TO_OUTDOORS, "Cinnabar Fly departure")
    landings = _fly_to_destination(actions, reader, emulator, MapId.FUCHSIA_CITY)
    final = reader.read()
    report = FuchsiaFlyArrivalReport(
        initial,
        final,
        initial_bag,
        _bag_tuple(emulator),
        dux_moves,
        dux_pp_before,
        _four(emulator, RamAddress.PARTY_MON_2_PP),
        landings,
        hp_before,
        _party_hp(emulator),
        max_hp_before,
        _party_max_hp(emulator),
        status_before,
        _party_status(emulator),
        actions.actions_executed,
        not emulator.pressed_buttons,
    )
    if not report.passed:
        raise FlyResourceError("Fuchsia Fly arrival evidence failed.")
    return report


def _fly_to_celadon(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> tuple[tuple[int, int], ...]:
    return _fly_to_destination(actions, reader, emulator, MapId.CELADON_CITY)


def _fly_to_destination(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    destination: MapId,
) -> tuple[tuple[int, int], ...]:
    landings: list[tuple[int, int]] = []
    attempts = [("up", steps) for steps in range(1, FLY_ATTEMPT_LIMIT // 2 + 1)]
    attempts += [("down", steps) for steps in range(1, FLY_ATTEMPT_LIMIT // 2 + 1)]
    for direction, steps in attempts:
        origin = reader.read().map_id
        if origin == destination:
            return tuple(landings)
        _open_fly_map(actions, reader, emulator)
        for _ in range(steps):
            _pulse(actions, MacroActionKind.MOVE, direction, frames=120)
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        landed = origin
        for index in range(6):
            _pulse(actions, MacroActionKind.WAIT, frames=90)
            landed = reader.read().map_id
            if landed != origin:
                break
            if index == 0:
                _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        raw = reader.read()
        if landed is None:
            raise FlyResourceError("Fly produced an unknown landing map.")
        landings.append((int(landed), int(raw.player_x or 0)))
        if landed == destination:
            return tuple(landings)
        if landed == origin:
            _close(actions, reader)
    raise FlyResourceError(
        f"Fly did not reach map {int(destination):#04x} in {len(attempts)} attempts."
    )


def _open_fly_map(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> None:
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.WAIT, frames=90)
    if reader.read().battle_state:
        raise FlyResourceError("Fly map opened into battle state.")


def _normalize_celadon_center(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
) -> None:
    raw = reader.read()
    if raw.map_id == MapId.CELADON_POKECENTER:
        if (raw.player_x, raw.player_y) == (3, 3):
            return
        if raw.player_x == 3 and raw.player_y is not None and 3 < raw.player_y <= 7:
            _move(actions, reader, ("up",) * (raw.player_y - 3), "Celadon nurse boundary")
            return
    if (
        raw.map_id != MapId.CELADON_CITY
        or raw.player_x is None
        or raw.player_y not in {10, 11}
        or not 41 <= raw.player_x <= 50
    ):
        raise FlyResourceError(
            "Celadon Center normalization saw an unsupported arrival: "
            f"map={raw.map_id}, coordinate={(raw.player_x, raw.player_y)!r}."
        )
    route = (
        ("up",) * (raw.player_y - 10)
        + ("left",) * (raw.player_x - 41)
        + ("up",) * 5
    )
    _move(actions, reader, route, "Celadon Center normalization")
    _require(reader.read(), MapId.CELADON_POKECENTER, (3, 3), "Celadon Center boundary")


def _checkpoint(
    records: list[FlyResourceCheckpoint],
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(FlyResourceCheckpoint(checkpoint_id, label, raw))


def _require(raw: RawGameState, map_id: MapId, coordinate: tuple[int, int], label: str) -> None:
    if (
        raw.map_id != map_id
        or (raw.player_x, raw.player_y) != coordinate
        or raw.battle_state != 0
    ):
        raise FlyResourceError(
            f"{label} missed gate: map={raw.map_id}, "
            f"coordinate={(raw.player_x, raw.player_y)!r}, battle={raw.battle_state}."
        )


def _pulse(
    actions: CountingExecutor,
    kind: MacroActionKind,
    value: str | None = None,
    frames: int = 240,
) -> None:
    actions.execute(MacroAction(kind, value))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _bag_tuple(emulator: EmulatorState) -> tuple[tuple[int, int], ...]:
    return tuple(sorted((int(item), count) for item, count in _bag(emulator).items()))


def _event(emulator: EmulatorState, event: EventFlag) -> bool:
    address = int(RamAddress.EVENT_FLAGS) + int(event) // 8
    return bool(emulator.read_u8(address) & (1 << (int(event) % 8)))
