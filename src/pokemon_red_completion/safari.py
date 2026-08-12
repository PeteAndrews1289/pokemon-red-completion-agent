"""Qualified one-admission Safari Zone HM03 Surf chapter."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.celadon import _bag, _money, _party_hp, _party_max_hp, _party_status
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
    DEFAULT_SILPH_TIMING,
    SILPH_PC_DEPOSIT_ITEMS,
    SilphChapterError,
    _deposit_pc_item,
)
from pokemon_red_completion.tower import party_core_intact

SAFARI_CHECKPOINT_COUNT = 12
GOLD_TEETH_CHECKPOINT_COUNT = 10
WATER_GUN = 0x37
SURF = 0x39
EXPECTED_MOVES_BEFORE = (0x2C, 0x27, 0x3D, WATER_GUN)
EXPECTED_MOVES_AFTER = (0x2C, 0x27, 0x3D, SURF)
SURF_PP = 15
EXPECTED_PP_AFTER = (25, 30, 20, SURF_PP)
PRE_SILPH_STRENGTH_MOVES_BEFORE_SURF = (0x2C, 0x46, 0x3D, WATER_GUN)
PRE_SILPH_STRENGTH_MOVES_AFTER_SURF = (0x2C, 0x46, 0x3D, SURF)
PRE_SILPH_STRENGTH_PP_AFTER_SURF = (25, 15, 20, SURF_PP)
POST_SILPH_MOVES_BEFORE_SURF = (0x2C, 0x46, 0x3A, WATER_GUN)
POST_SILPH_MOVES_AFTER_SURF = (0x2C, 0x46, 0x3A, SURF)
POST_SILPH_PP_AFTER_SURF = (25, 15, 10, SURF_PP)
SURF_MOVE_LINEAGES: dict[tuple[int, ...], tuple[tuple[int, ...], tuple[int, ...]]] = {
    EXPECTED_MOVES_BEFORE: (EXPECTED_MOVES_AFTER, EXPECTED_PP_AFTER),
    PRE_SILPH_STRENGTH_MOVES_BEFORE_SURF: (
        PRE_SILPH_STRENGTH_MOVES_AFTER_SURF,
        PRE_SILPH_STRENGTH_PP_AFTER_SURF,
    ),
    POST_SILPH_MOVES_BEFORE_SURF: (
        POST_SILPH_MOVES_AFTER_SURF,
        POST_SILPH_PP_AFTER_SURF,
    ),
}


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[item] for item in value)


FUCHSIA_APPROACH = (
    "URRRUURUUUUUUUUUULUURRRRRRDRRURRRRUUUUUURRUUUUUU"
    "LLLLLLLLLLLLLLLDDLLLLU"
)
CENTER_TO_GATE = _directions("DDDDDD" + FUCHSIA_APPROACH)
CENTER_TO_EAST = _directions("UUUUUUUUURRRRRUURRUUURRRRRRRR")
EAST_TO_NORTH = _directions(
    "RRRRDRRRRRRRRRRRRRUURRRUULLLLLLLLDDLLLUUUUUUURUURULUUUURRUURRRRR"
    "DDRRRUUUUULLLLLLLLLLLDDLLLLLLLLLL"
)
# The shorter x=8/9 south warp reaches West's isolated elevation shelf.  The
# x=2/3 warp below is the source-qualified route to the Teeth/Secret House.
NORTH_TO_WEST = _directions(
    "ULLULLLLLLLLLLLLUUUUULLLUULLLLDDDDLLDDLLLUUUUUUUUUUUUUUUUUUUUUU"
    "RRRRRRRRRURRRRRRUULLLLLLLLLLLLLLLLLLDDDDLLLDDDDDDLLLL"
    "DDDDDDDDDDDDDDDDDDDDDDD"
)
WEST_TO_TEETH = _directions("DDDDDDDDLL")
TEETH_TO_HOUSE = _directions("UUULLLLLLLLLLDLLLLUULLU")
HOUSE_TO_GURU = _directions("UUUR")
HOUSE_EXIT = _directions("DDDD")
# The outward Fuchsia path crosses one-way fence/ledge geometry and is not
# reversible: a literal inverse blocks at (24, 26).  This independently
# qualified return stays on the legal south/east passages to the Center.
GATE_TO_CENTER = _directions(
    "RRRRUURRRRRRRRRRRRRRRDDDDDDDDDDDDLLDLLLLLLULLLLLLDDDDDDDLLLLLLLLLL"
    "LLLLLLLLLLLLDDDDDDDDDDDRRRRRRRUUUURRRRRRRRRRRU"
)


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class SafariChapterError(RuntimeError):
    """Raised when the one-admission Surf evidence contract fails."""


@dataclass(frozen=True, slots=True)
class SafariTiming:
    wait_frames: int = 180
    movement_frames: int = 240
    movement_retries: int = 18
    dialogue_pulses: int = 40
    cleanup_pulses: int = 24

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_SAFARI_TIMING = SafariTiming()


@dataclass(frozen=True, slots=True)
class SafariProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[SafariProgress], None]


@dataclass(frozen=True, slots=True)
class SafariCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState
    steps: int
    balls: int


@dataclass(frozen=True, slots=True)
class SafariChapterReport:
    records: tuple[SafariCheckpoint, ...]
    final_raw: RawGameState
    initial_bag: tuple[tuple[int, int], ...]
    final_bag: tuple[tuple[int, int], ...]
    initial_money: int
    final_money: int
    counter_milestones: tuple[int, ...]
    balls_milestones: tuple[int, ...]
    got_tm40_skull_bash: bool
    gold_teeth: bool
    gold_teeth_precollected: bool
    got_hm03: bool
    hm03_retained: bool
    in_safari_zone: bool
    safari_steps: int
    safari_balls: int
    capacity_ready: bool
    moves_before: tuple[int, ...]
    moves_after: tuple[int, ...]
    pp_before: tuple[int, ...]
    pp_after_teach: tuple[int, ...]
    pp_after: tuple[int, ...]
    encounters_fled: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        lineage = SURF_MOVE_LINEAGES.get(self.moves_before)
        new_items = (
            ((int(ItemId.HM03_SURF), 1),)
            if self.gold_teeth_precollected
            else (
                (int(ItemId.GOLD_TEETH), 1),
                (int(ItemId.HM03_SURF), 1),
                (int(ItemId.TM40_SKULL_BASH), 1),
            )
        )
        expected_final_bag = tuple(sorted((*self.initial_bag, *new_items)))
        return (
            len(self.records) == SAFARI_CHECKPOINT_COUNT
            and self.initial_money - self.final_money == 500
            and self.counter_milestones == (500, 472, 376, 238, 228, 201, 0)
            and self.balls_milestones == (30,) * 7
            and self.got_tm40_skull_bash
            and (self.gold_teeth != self.gold_teeth_precollected)
            and self.got_hm03
            and self.hm03_retained
            and not self.in_safari_zone
            and self.safari_steps == 0
            and self.safari_balls == 0
            and self.capacity_ready
            and lineage is not None
            and self.moves_after == lineage[0]
            and len(self.pp_before) == 4
            and self.pp_after_teach == (*self.pp_before[:3], SURF_PP)
            and self.pp_after == lineage[1]
            and 0 <= self.encounters_fled <= 20
            and self.final_bag == expected_final_bag
            and self.final_raw.map_id == MapId.FUCHSIA_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.party_hp == self.party_max_hp
            and all(status == 0 for status in self.party_status)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "obtain_surf",
            "admission": {
                "fee": self.initial_money - self.final_money,
                "initial_steps": self.counter_milestones[0],
                "initial_balls": self.balls_milestones[0],
                "single_admission": True,
            },
            "inventory_capacity_ready": self.capacity_ready,
            "route": {
                "step_milestones": list(self.counter_milestones),
                "balls_milestones": list(self.balls_milestones),
                "west_elevation_trap_avoided": True,
                "encounters_fled": self.encounters_fled,
            },
            "rewards": {
                "tm40_skull_bash": self.got_tm40_skull_bash,
                "gold_teeth": self.gold_teeth,
                "gold_teeth_precollected": self.gold_teeth_precollected,
                "got_hm03_event": self.got_hm03,
                "hm03_reusable_and_retained": self.hm03_retained,
            },
            "surf": {
                "move_id": SURF,
                "replaced_move_id": WATER_GUN,
                "slot": 4,
                "moves_before": list(self.moves_before),
                "moves_after": list(self.moves_after),
                "pp_before": list(self.pp_before),
                "pp_after_teach": list(self.pp_after_teach),
                "pp_after": list(self.pp_after),
            },
            "cleanup": {
                "mechanism": "times_up",
                "steps": self.safari_steps,
                "balls": self.safari_balls,
                "in_safari_zone": self.in_safari_zone,
            },
            "money_remaining": self.final_money,
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


@dataclass(frozen=True, slots=True)
class GoldTeethChapterReport:
    """Evidence for the independent Gold Teeth resource lesson."""

    records: tuple[SafariCheckpoint, ...]
    final_raw: RawGameState
    initial_bag: tuple[tuple[int, int], ...]
    final_bag: tuple[tuple[int, int], ...]
    initial_money: int
    final_money: int
    counter_milestones: tuple[int, ...]
    balls_milestones: tuple[int, ...]
    got_tm40_skull_bash: bool
    gold_teeth: bool
    got_hm03: bool
    in_safari_zone: bool
    safari_steps: int
    safari_balls: int
    moves_before: tuple[int, ...]
    moves_after: tuple[int, ...]
    pp_after: tuple[int, ...]
    encounters_fled: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        expected_final_bag = tuple(
            sorted(
                (
                    *self.initial_bag,
                    (int(ItemId.GOLD_TEETH), 1),
                    (int(ItemId.TM40_SKULL_BASH), 1),
                )
            )
        )
        return (
            len(self.records) == GOLD_TEETH_CHECKPOINT_COUNT
            and self.initial_money - self.final_money == 500
            and self.counter_milestones == (500, 472, 376, 238, 228, 0)
            and self.balls_milestones == (30,) * 6
            and self.got_tm40_skull_bash
            and self.gold_teeth
            and not self.got_hm03
            and not self.in_safari_zone
            and self.safari_steps == 0
            and self.safari_balls == 0
            and self.moves_before == EXPECTED_MOVES_BEFORE
            and self.moves_after == EXPECTED_MOVES_BEFORE
            and self.pp_after == (25, 30, 20, 25)
            and 0 <= self.encounters_fled <= 20
            and self.final_bag == expected_final_bag
            and self.final_raw.map_id == MapId.FUCHSIA_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.party_hp == self.party_max_hp
            and all(status == 0 for status in self.party_status)
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "resource": "gold_teeth",
            "objective_added": False,
            "admission": {
                "fee": self.initial_money - self.final_money,
                "initial_steps": self.counter_milestones[0],
                "initial_balls": self.balls_milestones[0],
                "single_admission": True,
            },
            "route": {
                "step_milestones": list(self.counter_milestones),
                "balls_milestones": list(self.balls_milestones),
                "encounters_fled": self.encounters_fled,
            },
            "rewards": {
                "tm40_skull_bash": self.got_tm40_skull_bash,
                "gold_teeth": self.gold_teeth,
                "hm03_untouched": not self.got_hm03,
            },
            "cleanup": {
                "mechanism": "times_up_before_secret_house",
                "steps": self.safari_steps,
                "balls": self.safari_balls,
                "in_safari_zone": self.in_safari_zone,
            },
            "money_remaining": self.final_money,
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


def run_gold_teeth_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: SafariTiming = DEFAULT_SAFARI_TIMING,
    progress: ProgressSink | None = None,
) -> GoldTeethChapterReport:
    """Collect Gold Teeth in one admission without entering the Secret House."""

    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[SafariCheckpoint] = []
    encounters = 0
    initial = reader.read()
    _require(initial, MapId.FUCHSIA_POKECENTER, (3, 3), "Fuchsia boundary")
    initial_bag = _bag_tuple(emulator)
    initial_money = _money(emulator)
    moves_before = tuple(initial.first_party_moves or ())
    if (
        moves_before != EXPECTED_MOVES_BEFORE
        or ItemId.GOLD_TEETH in _bag(emulator)
        or ItemId.HM03_SURF in _bag(emulator)
        or ItemId.TM40_SKULL_BASH in _bag(emulator)
        or _event(emulator, EventFlag.GOT_HM03)
    ):
        raise SafariChapterError("Gold Teeth input boundary is not pristine.")
    _checkpoint(records, progress, emulator, initial, "teeth_ready", "Gold Teeth route ready")

    encounters += _move(actions, reader, emulator, CENTER_TO_GATE, timing, "Safari gate")
    _require(reader.read(), MapId.SAFARI_ZONE_GATE, (3, 5), "Safari gate")
    _checkpoint(records, progress, emulator, reader.read(), "gate", "Reached Safari gate")
    _move(actions, reader, emulator, ("up", "up", "up"), timing, "Safari clerk")
    for _ in range(timing.dialogue_pulses):
        raw = reader.read()
        if raw.map_id == MapId.SAFARI_ZONE_CENTER:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise SafariChapterError("Safari admission did not enter Center.")
    _require(raw, MapId.SAFARI_ZONE_CENTER, (15, 25), "Safari admission")
    if initial_money - _money(emulator) != 500 or _steps(emulator) != 500 or _balls(emulator) != 30:
        raise SafariChapterError("Safari admission fee/counter initialization mismatch.")
    milestones = [_steps(emulator)]
    ball_milestones = [_balls(emulator)]
    _checkpoint(records, progress, emulator, raw, "admitted", "Paid once and entered Safari Center")

    for route, map_id, coordinate, expected_steps, checkpoint_id, label in (
        (CENTER_TO_EAST, MapId.SAFARI_ZONE_EAST, (0, 23), 472, "east", "Reached East"),
        (EAST_TO_NORTH, MapId.SAFARI_ZONE_NORTH, (39, 31), 376, "north", "Reached North"),
        (
            NORTH_TO_WEST,
            MapId.SAFARI_ZONE_WEST,
            (21, 0),
            238,
            "west",
            "Reached West through correct elevation",
        ),
        (
            WEST_TO_TEETH,
            MapId.SAFARI_ZONE_WEST,
            (19, 8),
            228,
            "teeth_stance",
            "Reached Gold Teeth",
        ),
    ):
        encounters += _move(actions, reader, emulator, route, timing, label)
        _require(reader.read(), map_id, coordinate, label)
        if _steps(emulator) != expected_steps or _balls(emulator) != 30:
            raise SafariChapterError(
                f"{label} counter mismatch: {_steps(emulator)}/{_balls(emulator)}."
            )
        milestones.append(_steps(emulator))
        ball_milestones.append(_balls(emulator))
        _checkpoint(records, progress, emulator, reader.read(), checkpoint_id, label)

    _pulse(actions, MacroActionKind.MOVE, "up", frames=timing.wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    if ItemId.GOLD_TEETH not in _bag(emulator):
        raise SafariChapterError("Gold Teeth pickup failed.")
    _checkpoint(records, progress, emulator, reader.read(), "teeth", "Collected Gold Teeth")

    while _steps(emulator) > 0:
        current = reader.read()
        direction = "right" if current.player_x == 19 else "left"
        encounters += _move(
            actions,
            reader,
            emulator,
            (direction,),
            timing,
            "Gold Teeth Times Up loop",
        )
    _pulse(actions, MacroActionKind.MOVE, "left", frames=timing.movement_frames)
    for _ in range(timing.cleanup_pulses):
        raw = reader.read()
        if (
            raw.map_id == MapId.SAFARI_ZONE_GATE
            and (raw.player_x, raw.player_y) == (4, 3)
            and reader.read_input_readiness().ready
        ):
            break
        kind = (
            MacroActionKind.CANCEL
            if raw.map_id == MapId.SAFARI_ZONE_GATE
            else MacroActionKind.CONFIRM
        )
        _pulse(actions, kind, frames=timing.wait_frames)
    else:
        raise SafariChapterError("Times Up cleanup did not return stable gate control.")
    if _steps(emulator) or _balls(emulator) or _event(emulator, EventFlag.IN_SAFARI_ZONE):
        raise SafariChapterError("Times Up cleanup left Safari state active.")
    milestones.append(0)
    ball_milestones.append(30)
    _checkpoint(records, progress, emulator, raw, "cleanup", "Times Up cleared Safari state")

    encounters += _move(actions, reader, emulator, ("down", "down", "down"), timing, "Gate exit")
    _require(reader.read(), MapId.FUCHSIA_CITY, (18, 4), "Gate exit")
    encounters += _move(actions, reader, emulator, GATE_TO_CENTER, timing, "Fuchsia Center return")
    _require(reader.read(), MapId.FUCHSIA_POKECENTER, (3, 7), "Center return")
    encounters += _move(actions, reader, emulator, ("up",) * 4, timing, "Fuchsia nurse")
    for _ in range(timing.dialogue_pulses):
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and all(status == 0 for status in _party_status(emulator))
            and reader.read().first_party_pp == (25, 30, 20, 25)
        ):
            break
    for _ in range(6):
        _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
    final = reader.read()
    _require(final, MapId.FUCHSIA_POKECENTER, (3, 3), "healed Gold Teeth boundary")
    _checkpoint(records, progress, emulator, final, "stable", "Healed Gold Teeth boundary")

    report = GoldTeethChapterReport(
        records=tuple(records),
        final_raw=final,
        initial_bag=initial_bag,
        final_bag=_bag_tuple(emulator),
        initial_money=initial_money,
        final_money=_money(emulator),
        counter_milestones=tuple(milestones),
        balls_milestones=tuple(ball_milestones),
        got_tm40_skull_bash=ItemId.TM40_SKULL_BASH in _bag(emulator),
        gold_teeth=ItemId.GOLD_TEETH in _bag(emulator),
        got_hm03=_event(emulator, EventFlag.GOT_HM03),
        in_safari_zone=_event(emulator, EventFlag.IN_SAFARI_ZONE),
        safari_steps=_steps(emulator),
        safari_balls=_balls(emulator),
        moves_before=moves_before,
        moves_after=tuple(final.first_party_moves or ()),
        pp_after=tuple(final.first_party_pp or ()),
        encounters_fled=encounters,
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise SafariChapterError(
            f"Gold Teeth evidence contract failed: {report.public_dict()!r}."
        )
    return report


def run_safari_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: SafariTiming = DEFAULT_SAFARI_TIMING,
    progress: ProgressSink | None = None,
) -> SafariChapterReport:
    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[SafariCheckpoint] = []
    encounters = 0
    initial = reader.read()
    _require(initial, MapId.FUCHSIA_POKECENTER, (3, 3), "Fuchsia boundary")
    initial_bag = _bag_tuple(emulator)
    initial_money = _money(emulator)
    moves_before = tuple(initial.first_party_moves or ())
    lineage = SURF_MOVE_LINEAGES.get(moves_before)
    if lineage is None:
        raise SafariChapterError(f"Unexpected pre-Surf moves: {moves_before!r}.")
    expected_moves_after, expected_pp_after = lineage
    gold_teeth_precollected = (
        moves_before != EXPECTED_MOVES_BEFORE
        and ItemId.TM40_SKULL_BASH in _bag(emulator)
        and ItemId.GOLD_TEETH not in _bag(emulator)
    )
    entry_bag = _bag(emulator)
    if len(entry_bag) >= 20:
        obsolete = next(
            (item for item in SILPH_PC_DEPOSIT_ITEMS if entry_bag.get(item, 0) == 1),
            None,
        )
        if not gold_teeth_precollected or obsolete is None:
            raise SafariChapterError("Surf input lacks one safe HM03 inventory slot.")
        _move(
            actions,
            reader,
            emulator,
            ("down",) + ("right",) * 10,
            timing,
            "Fuchsia PC approach",
        )
        try:
            _deposit_pc_item(
                actions,  # type: ignore[arg-type]
                reader,
                emulator,
                obsolete,
                DEFAULT_SILPH_TIMING,
            )
        except SilphChapterError as error:
            raise SafariChapterError("Surf inventory cleanup failed.") from error
        _move(
            actions,
            reader,
            emulator,
            ("left",) * 10 + ("up",),
            timing,
            "Fuchsia PC return",
        )
        _require(reader.read(), MapId.FUCHSIA_POKECENTER, (3, 3), "post-cleanup boundary")
    initial_bag = _bag_tuple(emulator)
    capacity_ready = len(initial_bag) <= 19
    if not capacity_ready:
        raise SafariChapterError("Surf inventory cleanup did not free an HM03 slot.")
    pp_before = tuple(initial.first_party_pp or ())
    if len(pp_before) != 4 or any(pp <= 0 for pp in pp_before):
        raise SafariChapterError(f"Unexpected pre-Surf PP: {pp_before!r}.")
    _checkpoint(records, progress, emulator, initial, "surf_ready", "Fuchsia Safari-ready")

    encounters += _move(actions, reader, emulator, CENTER_TO_GATE, timing, "Safari gate")
    _require(reader.read(), MapId.SAFARI_ZONE_GATE, (3, 5), "Safari gate")
    _checkpoint(records, progress, emulator, reader.read(), "gate", "Reached Safari gate")
    _move(actions, reader, emulator, ("up", "up", "up"), timing, "Safari clerk")
    for _ in range(timing.dialogue_pulses):
        raw = reader.read()
        if raw.map_id == MapId.SAFARI_ZONE_CENTER:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise SafariChapterError("Safari admission did not enter Center.")
    _require(raw, MapId.SAFARI_ZONE_CENTER, (15, 25), "Safari admission")
    if initial_money - _money(emulator) != 500 or _steps(emulator) != 500 or _balls(emulator) != 30:
        raise SafariChapterError("Safari admission fee/counter initialization mismatch.")
    milestones = [_steps(emulator)]
    ball_milestones = [_balls(emulator)]
    _checkpoint(records, progress, emulator, raw, "admitted", "Paid once and entered Safari Center")

    for route, map_id, coordinate, expected_steps, checkpoint_id, label in (
        (CENTER_TO_EAST, MapId.SAFARI_ZONE_EAST, (0, 23), 472, "east", "Reached East"),
        (EAST_TO_NORTH, MapId.SAFARI_ZONE_NORTH, (39, 31), 376, "north", "Reached North"),
        (
            NORTH_TO_WEST,
            MapId.SAFARI_ZONE_WEST,
            (21, 0),
            238,
            "west",
            "Reached West through correct elevation",
        ),
        (
            WEST_TO_TEETH,
            MapId.SAFARI_ZONE_WEST,
            (19, 8),
            228,
            "teeth_stance",
            "Reached Gold Teeth",
        ),
    ):
        encounters += _move(actions, reader, emulator, route, timing, label)
        _require(reader.read(), map_id, coordinate, label)
        if _steps(emulator) != expected_steps or _balls(emulator) != 30:
            raise SafariChapterError(
                f"{label} counter mismatch: {_steps(emulator)}/{_balls(emulator)}."
            )
        milestones.append(_steps(emulator))
        ball_milestones.append(_balls(emulator))
        _checkpoint(records, progress, emulator, reader.read(), checkpoint_id, label)

    if gold_teeth_precollected:
        _checkpoint(
            records,
            progress,
            emulator,
            reader.read(),
            "teeth",
            "Verified prior Gold Teeth route",
        )
    else:
        _pulse(actions, MacroActionKind.MOVE, "up", frames=timing.wait_frames)
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
        if ItemId.GOLD_TEETH not in _bag(emulator):
            raise SafariChapterError("Gold Teeth pickup failed.")
        _checkpoint(records, progress, emulator, reader.read(), "teeth", "Collected Gold Teeth")

    encounters += _move(actions, reader, emulator, TEETH_TO_HOUSE, timing, "Secret House")
    _require(reader.read(), MapId.SAFARI_ZONE_SECRET_HOUSE, (2, 7), "Secret House")
    if _steps(emulator) != 205:
        raise SafariChapterError(f"Secret House expected 205 steps, saw {_steps(emulator)}.")
    encounters += _move(actions, reader, emulator, HOUSE_TO_GURU, timing, "Surf guru")
    _require(reader.read(), MapId.SAFARI_ZONE_SECRET_HOUSE, (3, 4), "Surf guru")
    _pulse(actions, MacroActionKind.MOVE, "up", frames=timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        if ItemId.HM03_SURF in _bag(emulator) and _event(emulator, EventFlag.GOT_HM03):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise SafariChapterError("Secret House did not award HM03.")
    _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
    if _steps(emulator) != 201 or _balls(emulator) != 30:
        raise SafariChapterError("HM03 reward counter/item invariant failed.")
    milestones.append(_steps(emulator))
    ball_milestones.append(_balls(emulator))
    _checkpoint(records, progress, emulator, reader.read(), "hm03", "Won reusable HM03")

    taught = _teach_surf(
        actions,
        reader,
        emulator,
        timing,
        pp_before=pp_before,
        expected_moves_after=expected_moves_after,
    )
    _checkpoint(records, progress, emulator, reader.read(), "surf", "Taught Surf over Water Gun")

    encounters += _move(actions, reader, emulator, HOUSE_EXIT, timing, "Secret House exit")
    _require(reader.read(), MapId.SAFARI_ZONE_WEST, (3, 4), "Secret House exit")
    while _steps(emulator) > 0:
        raw = reader.read()
        direction = "right" if raw.player_x == 3 else "left"
        encounters += _move(actions, reader, emulator, (direction,), timing, "Times Up loop")
    _pulse(actions, MacroActionKind.MOVE, "left", frames=timing.movement_frames)
    for _ in range(timing.cleanup_pulses):
        raw = reader.read()
        if (
            raw.map_id == MapId.SAFARI_ZONE_GATE
            and (raw.player_x, raw.player_y) == (4, 3)
            and reader.read_input_readiness().ready
        ):
            break
        kind = (
            MacroActionKind.CANCEL
            if raw.map_id == MapId.SAFARI_ZONE_GATE
            else MacroActionKind.CONFIRM
        )
        _pulse(actions, kind, frames=timing.wait_frames)
    else:
        raise SafariChapterError("Times Up cleanup did not return stable gate control.")
    if _steps(emulator) or _balls(emulator) or _event(emulator, EventFlag.IN_SAFARI_ZONE):
        raise SafariChapterError("Times Up cleanup left Safari state active.")
    milestones.append(0)
    ball_milestones.append(30)
    _checkpoint(records, progress, emulator, raw, "cleanup", "Times Up cleared Safari state")

    encounters += _move(actions, reader, emulator, ("down", "down", "down"), timing, "Gate exit")
    _require(reader.read(), MapId.FUCHSIA_CITY, (18, 4), "Gate exit")
    encounters += _move(actions, reader, emulator, GATE_TO_CENTER, timing, "Fuchsia Center return")
    _require(reader.read(), MapId.FUCHSIA_POKECENTER, (3, 7), "Center return")
    encounters += _move(actions, reader, emulator, ("up",) * 4, timing, "Fuchsia nurse")
    for _ in range(timing.dialogue_pulses):
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
        if _party_hp(emulator) == _party_max_hp(emulator) and all(
            status == 0 for status in _party_status(emulator)
        ) and reader.read().first_party_pp == expected_pp_after:
            break
    for _ in range(6):
        _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
    final = reader.read()
    _require(final, MapId.FUCHSIA_POKECENTER, (3, 3), "healed Surf boundary")
    _checkpoint(records, progress, emulator, final, "stable", "Healed Surf-ready Fuchsia boundary")

    report = SafariChapterReport(
        tuple(records),
        final,
        initial_bag,
        _bag_tuple(emulator),
        initial_money,
        _money(emulator),
        tuple(milestones),
        tuple(ball_milestones),
        ItemId.TM40_SKULL_BASH in _bag(emulator),
        ItemId.GOLD_TEETH in _bag(emulator),
        gold_teeth_precollected,
        _event(emulator, EventFlag.GOT_HM03),
        ItemId.HM03_SURF in _bag(emulator),
        _event(emulator, EventFlag.IN_SAFARI_ZONE),
        _steps(emulator),
        _balls(emulator),
        capacity_ready,
        moves_before,
        tuple(final.first_party_moves or ()),
        pp_before,
        tuple(taught.first_party_pp or ()),
        tuple(final.first_party_pp or ()),
        encounters,
        _party_hp(emulator),
        _party_max_hp(emulator),
        _party_status(emulator),
        emulator.frame_count - start_frames,
        actions.actions_executed,
        not emulator.pressed_buttons,
    )
    if not report.passed:
        raise SafariChapterError(f"Safari evidence contract failed: {report.public_dict()!r}.")
    return report


def _teach_surf(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SafariTiming,
    *,
    pp_before: tuple[int, ...],
    expected_moves_after: tuple[int, ...],
) -> RawGameState:
    actions.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(actions, timing.wait_frames)
    _select_cursor(actions, emulator, 2, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _select_bag_item(actions, emulator, ItemId.HM03_SURF, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        if _menu_origin(emulator) == (0, 1):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise SafariChapterError("HM03 did not reach party selection.")
    _select_cursor(actions, emulator, 0, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        if _menu_origin(emulator) == (5, 8):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise SafariChapterError("HM03 did not reach move deletion.")
    _select_cursor(actions, emulator, 3, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        raw = reader.read()
        if (
            raw.first_party_moves == expected_moves_after
            and raw.first_party_pp == (*pp_before[:3], SURF_PP)
            and ItemId.HM03_SURF in _bag(emulator)
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise SafariChapterError("HM03 did not replace slot-four Water Gun.")
    for _ in range(4):
        _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
    return raw


def _move(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    directions: Iterable[str],
    timing: SafariTiming,
    label: str,
) -> int:
    encounters = 0
    state = reader.read()
    for step, direction in enumerate(directions, 1):
        before = (state.map_id, state.player_x, state.player_y)
        for _ in range(timing.movement_retries):
            _pulse(actions, MacroActionKind.MOVE, direction, frames=timing.movement_frames)
            state = reader.read()
            if state.battle_state == 1:
                _flee_safari(actions, reader, emulator, timing)
                encounters += 1
                state = reader.read()
            if (state.map_id, state.player_x, state.player_y) != before:
                if (
                    label == "Reached West through correct elevation"
                    and state.map_id == MapId.SAFARI_ZONE_NORTH
                    and (state.player_x, state.player_y) == (19, 6)
                    and ItemId.TM40_SKULL_BASH not in _bag(emulator)
                ):
                    _pickup_tm40_skull_bash(actions, reader, emulator, timing)
                    state = reader.read()
                break
            if not reader.read_input_readiness().ready:
                _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
                state = reader.read()
        else:
            raise SafariChapterError(
                f"{label} blocked at step {step}: {direction}; "
                f"{(state.map_id, state.player_x, state.player_y)!r}."
            )
        if not party_core_intact(state.party_species_ids) or _balls(emulator) not in {0, 30}:
            raise SafariChapterError(f"{label} changed party or Safari Balls.")
    return encounters


def _pickup_tm40_skull_bash(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SafariTiming,
) -> None:
    """Collect the source-pinned North-area TM without spending a Safari step."""

    before_steps = _steps(emulator)
    _pulse(actions, MacroActionKind.MOVE, "down", frames=timing.wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        if ItemId.TM40_SKULL_BASH in _bag(emulator):
            for _ in range(4):
                _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
            final = reader.read()
            if (
                final.map_id != MapId.SAFARI_ZONE_NORTH
                or (final.player_x, final.player_y) != (19, 6)
                or _steps(emulator) != before_steps
            ):
                raise SafariChapterError("TM40 pickup changed the qualified Safari route.")
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise SafariChapterError("North-area TM40 Skull Bash pickup failed.")


def _flee_safari(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SafariTiming,
) -> None:
    bag = _bag_tuple(emulator)
    hp = _party_hp(emulator)
    balls = _balls(emulator)
    for _ in range(12):
        if reader.read().battle_state == 0:
            break
        for kind, direction in (
            (MacroActionKind.CANCEL, None),
            (MacroActionKind.MOVE, "down"),
            (MacroActionKind.MOVE, "right"),
            (MacroActionKind.CONFIRM, None),
        ):
            _pulse(actions, kind, direction, frames=timing.wait_frames)
            if reader.read().battle_state == 0:
                break
    else:
        raise SafariChapterError("Safari RUN did not end encounter.")
    if _bag_tuple(emulator) != bag or _party_hp(emulator) != hp or _balls(emulator) != balls:
        raise SafariChapterError("Safari RUN changed protected inventory/party/Balls.")


def _select_cursor(
    actions: CountingExecutor,
    emulator: EmulatorState,
    target: int,
    timing: SafariTiming,
) -> None:
    for _ in range(16):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target:
            return
        _pulse(
            actions,
            MacroActionKind.MOVE,
            "down" if cursor < target else "up",
            frames=min(timing.wait_frames, 120),
        )
    raise SafariChapterError(f"Menu cursor could not select {target}.")


def _select_bag_item(
    actions: CountingExecutor,
    emulator: EmulatorState,
    item: int,
    timing: SafariTiming,
) -> None:
    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        items = tuple(_bag(emulator))
        if absolute < len(items) and items[absolute] == item:
            return
        _pulse(actions, MacroActionKind.MOVE, "down", frames=min(timing.wait_frames, 120))
    raise SafariChapterError(f"Bag could not select {item:#04x}.")


def _menu_origin(emulator: EmulatorState) -> tuple[int, int]:
    return (
        emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
        emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
    )


def _steps(emulator: EmulatorState) -> int:
    return (emulator.read_u8(RamAddress.SAFARI_STEPS) << 8) | emulator.read_u8(
        RamAddress.SAFARI_STEPS + 1
    )


def _balls(emulator: EmulatorState) -> int:
    return emulator.read_u8(RamAddress.SAFARI_BALLS)


def _event(emulator: EmulatorState, event: EventFlag) -> bool:
    value = int(event)
    return bool(emulator.read_u8(int(RamAddress.EVENT_FLAGS) + value // 8) & (1 << (value % 8)))


def _bag_tuple(emulator: EmulatorState) -> tuple[tuple[int, int], ...]:
    return tuple(sorted((int(item), count) for item, count in Counter(_bag(emulator)).items()))


def _require(raw: RawGameState, map_id: int, coordinate: tuple[int, int], label: str) -> None:
    if (
        raw.map_id != map_id
        or (raw.player_x, raw.player_y) != coordinate
        or raw.battle_state != 0
        or not party_core_intact(raw.party_species_ids)
    ):
        raise SafariChapterError(
            f"{label} missed gate: map={raw.map_id!r}, "
            f"coordinate={(raw.player_x, raw.player_y)!r}, battle={raw.battle_state!r}."
        )


def _checkpoint(
    records: list[SafariCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(SafariCheckpoint(checkpoint_id, label, raw, _steps(emulator), _balls(emulator)))
    if progress is not None:
        progress(
            SafariProgress(
                checkpoint_id,
                label,
                len(records),
                SAFARI_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _pulse(
    actions: CountingExecutor,
    kind: MacroActionKind,
    value: str | int | None = None,
    *,
    frames: int,
) -> None:
    actions.execute(MacroAction(kind, value))
    _wait(actions, frames)


def _wait(actions: CountingExecutor, frames: int) -> None:
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
