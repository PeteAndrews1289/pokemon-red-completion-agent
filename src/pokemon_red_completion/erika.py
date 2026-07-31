"""Qualified Fuchsia-to-Celadon traversal and Rainbow Badge chapter."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRuntimeError,
    BattleRuntimeTiming,
    RequiredMovePolicy,
    run_adaptive_trainer_battle,
)
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
from pokemon_red_completion.economy import POST_ERIKA_MONEY, POST_KOGA_MONEY
from pokemon_red_completion.lavender import (
    LavenderTiming,
    _close_menus,
    _open_bag,
    _select_bag_item,
    _select_cursor,
)
from pokemon_red_completion.observation import (
    Badge,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref
from pokemon_red_completion.tower import TOWER_FINAL_PARTY

ERIKA_CHECKPOINT_COUNT = 12
STRENGTH = 0x46
ERIKA_OPPONENT = 0xED
ERIKA_CLASS = 0x25
SKULL_BASH = 0x82
GYM_EVENTS = tuple(
    EventFlag(int(EventFlag.BEAT_CELADON_GYM_TRAINER_0) + index) for index in range(7)
)
OPTIONAL_ROUTE_EVENTS = tuple(
    EventFlag(int(EventFlag.BEAT_ROUTE_14_TRAINER_0) + index) for index in range(10)
) + tuple(EventFlag(int(EventFlag.BEAT_ROUTE_15_TRAINER_0) + index) for index in range(10))


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[c] for c in value)


FUCHSIA_EXIT = _directions("DDDDDD")
FUCHSIA_TO_ROUTE15 = _directions("URRRUURUUUUUUUURRRRRRURRRRRRRRRR")
ROUTE15_GATE_IN = _directions("R" * 8)
ROUTE15_GATE_OUT = _directions("R" * 8)
ROUTE15_TO_14 = _directions("RRRRRRURRRRRRRRRRRRRRRRRRRRRRRRRRDRRRRRRRRRRRRRR")
ROUTE14_TO_13 = _directions("URRRURRRUUURRRRRUUUUUUURURRRRUUULULUUUUUUUUUUUULUUUUUURRRRRRR")
ROUTE13_TO_12 = _directions(
    "RRRRUURRRRRRRUURURRRURRRRRRRRRDDLLLLLLLDDRRRRRRRRRDDLDDRRRRRRRRRURRRRRRRRRRRRRRRRUURUUUUUUUUUU"
)
ROUTE12_TO_GATE = _directions(
    "UUURUUUUUURRUUUULLLULLLLLUUURURURRUUUUUULLLLLUUUURRRRRRRRRURUUUUU"
    "LLLLUUUUUUUULUUUUUUUULLLLLUUUUUUURRRDDDDRRRRRRUUULUUUUUULLLLUUULL"
    "ULLLUUUUUURRRRRRUUUURRRRUUUULLLUUUULU"
)
ROUTE12_GATE = _directions("U" * 8)
ROUTE12_TO_LAVENDER = _directions("UUUUULUUUUUUUUUUU")
LAVENDER_TO_ROUTE8 = _directions("UUULLLLLLLLUUUUUULL")
ROUTE8_TO_GATE = _directions(
    "LLLLDDDDDLLLLLULLLLUUUUULLLLLULLLLLLLLLLLLDLDDDDDLLLLLLLLLLLLUUUUUUUULLLU"
)
GATE_TO_TUNNEL = _directions("RUUU")
TUNNEL = _directions("DDD" + "L" * 45)
ROUTE7_GATE = _directions("DDDD")
ROUTE7_TO_CELADON = _directions("RRRUUUUUULLLLUUUUULLLLL")
CELADON_CENTER_ENTRY = _directions("ULLLLLLLLU")
CENTER_EXIT = _directions("DDDDD")
CITY_TO_OUTER_TREE = _directions("DDDLDLLLDDDDDDDDDLLLLLLLLLLLLDDDDDRRRRRRRRRRDDD")
LOWER_CITY_TO_GYM = _directions("DDLLULLLLLLLLLLLLULLLLLLLLLLLLLLLLUUURRRRRRRU")
GYM_EXIT = _directions("DDLDDDDDDDDD")
GYM_TO_OUTER_TREE_SOUTH = _directions("RRRRRDDDRRRRDRRRRRRRRRRRRDRRU")
OUTER_TREE_TO_CENTER = _directions("UUUULLLLLLLLLLUUUUURURRRRRRRRRRUUUUUUUUUUUURRRRRU")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class ErikaChapterError(RuntimeError):
    """Raised when the Rainbow Badge evidence contract fails."""


@dataclass(frozen=True, slots=True)
class ErikaTiming:
    movement_frames: int = 240
    movement_retries: int = 8
    dialogue_pulses: int = 40
    cut_pulses: int = 8
    heal_pulses: int = 24
    battle_recoveries: int = 8

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_ERIKA_TIMING = ErikaTiming()


@dataclass(frozen=True, slots=True)
class ErikaProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[ErikaProgress], None]


@dataclass(frozen=True, slots=True)
class ErikaCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class ErikaChapterReport:
    records: tuple[ErikaCheckpoint, ...]
    final_raw: RawGameState
    erika_identity: tuple[int, int, int, int]
    strength_pp_spent: int
    moves_before: tuple[int, ...]
    moves_after: tuple[int, ...]
    money_before: int
    money_after: int
    badge_bits: int
    beat_gym_flags: int
    got_tm21: bool
    beat_erika: bool
    gym_events_before: tuple[bool, ...]
    gym_events_after: tuple[bool, ...]
    optional_route_events_before: tuple[bool, ...]
    optional_route_events_after: tuple[bool, ...]
    final_bag: tuple[tuple[int, int], ...]
    party_hp: tuple[int, int, int]
    party_max_hp: tuple[int, int, int]
    party_status: tuple[int, int, int]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == ERIKA_CHECKPOINT_COUNT
            and self.erika_identity == (ERIKA_OPPONENT, ERIKA_CLASS, ERIKA_OPPONENT, 1)
            and 0 < self.strength_pp_spent <= 10
            and self.moves_before == (0x2C, STRENGTH, 0x3D, 0x39)
            and self.moves_after == (0x82, STRENGTH, 0x3D, 0x39)
            and self.money_before == POST_KOGA_MONEY
            and self.money_after == POST_ERIKA_MONEY
            and self.badge_bits == 0x1F
            and self.beat_gym_flags & int(Badge.RAINBOW)
            and self.got_tm21
            and self.beat_erika
            and self.gym_events_before == (False,) * 7
            and self.gym_events_after == (True,) * 7
            and self.optional_route_events_before == (False,) * 20
            and self.optional_route_events_after == (False,) * 20
            and dict(self.final_bag).get(int(ItemId.TM21_MEGA_DRAIN)) == 1
            and self.final_raw.map_id == MapId.CELADON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.party_species_ids == TOWER_FINAL_PARTY
            and self.final_raw.first_party_level is not None
            and 42 <= self.final_raw.first_party_level <= 43
            and self.final_raw.first_party_moves == (0x82, STRENGTH, 0x3D, 0x39)
            and self.final_raw.first_party_pp == (15, 15, 20, 15)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and self.final_raw.first_party_hp == self.party_hp[0]
            and self.final_raw.first_party_max_hp == self.party_max_hp[0]
            and self.party_status == (0, 0, 0)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "defeat_erika",
            "erika": {
                "opponent": self.erika_identity[0],
                "class": self.erika_identity[1],
                "set": self.erika_identity[3],
                "strength_move_id": STRENGTH,
                "strength_pp_spent": self.strength_pp_spent,
                "level_42_move_learning": {
                    "slot": 1,
                    "replaced_move_id": 0x2C,
                    "learned_move_id": 0x82,
                    "moves_before": list(self.moves_before),
                    "moves_after": list(self.moves_after),
                    "learned_move_pp": 15,
                },
            },
            "rainbow_badge": {
                "obtained_badges": self.badge_bits,
                "beat_gym_flags": self.beat_gym_flags,
                "beat_erika": self.beat_erika,
                "got_tm21": self.got_tm21,
            },
            "money_remaining": self.money_after,
            "party": {
                "lead_level": self.final_raw.first_party_level,
                "hp": list(self.party_hp),
                "max_hp": list(self.party_max_hp),
                "status": list(self.party_status),
                "moves": list(self.moves_after),
                "pp": list(self.final_raw.first_party_pp or ()),
            },
            "optional_route_trainers_bypassed": sum(
                not defeated for defeated in self.optional_route_events_after
            ),
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


def run_erika_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: ErikaTiming = DEFAULT_ERIKA_TIMING,
    progress: ProgressSink | None = None,
) -> ErikaChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[ErikaCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.FUCHSIA_POKECENTER, (3, 3), "Strength boundary")
    if (
        _money(emulator) != POST_KOGA_MONEY
        or initial.first_party_pp != (25, 15, 20, 15)
        or _event(emulator, EventFlag.BEAT_ERIKA)
        or ItemId.TM21_MEGA_DRAIN in _bag(emulator)
    ):
        raise ErikaChapterError("Erika input boundary is not pristine.")
    events_before = _gym_events(emulator)
    optional_events_before = _optional_route_events(emulator)
    _checkpoint(records, progress, emulator, initial, "erika_ready", "Strength boundary ready")

    route_legs = (
        (FUCHSIA_EXIT, MapId.FUCHSIA_CITY, (19, 29), "fuchsia_exited"),
        (FUCHSIA_TO_ROUTE15, MapId.ROUTE_15, (0, 9), "route15_west"),
        (ROUTE15_GATE_IN, MapId.ROUTE_15_GATE_1F, (0, 5), "route15_gate"),
        (ROUTE15_GATE_OUT, MapId.ROUTE_15, (14, 9), "route15_east"),
        (ROUTE15_TO_14, MapId.ROUTE_14, (0, 45), "route14"),
        (ROUTE14_TO_13, MapId.ROUTE_13, (0, 10), "route13"),
        (ROUTE13_TO_12, MapId.ROUTE_12, (11, 107), "route12_south"),
        (ROUTE12_TO_GATE, MapId.ROUTE_12_GATE_1F, (4, 7), "route12_gate"),
        (ROUTE12_GATE, MapId.ROUTE_12, (10, 15), "route12_north"),
        (ROUTE12_TO_LAVENDER, MapId.LAVENDER_TOWN, (9, 17), "lavender"),
        (LAVENDER_TO_ROUTE8, MapId.ROUTE_8, (59, 8), "route8"),
        (ROUTE8_TO_GATE, MapId.UNDERGROUND_PATH_ROUTE_8, (3, 7), "route8_gate"),
        (GATE_TO_TUNNEL, MapId.UNDERGROUND_PATH_WEST_EAST, (47, 2), "tunnel_east"),
        (TUNNEL, MapId.UNDERGROUND_PATH_ROUTE_7, (4, 4), "tunnel_west"),
        (ROUTE7_GATE, MapId.ROUTE_7, (5, 14), "route7"),
        (ROUTE7_TO_CELADON, MapId.CELADON_CITY, (49, 11), "celadon"),
        (CELADON_CENTER_ENTRY, MapId.CELADON_POKECENTER, (3, 7), "celadon_center"),
    )
    for route, map_id, coordinate, label in route_legs:
        _move(actions, reader, emulator, route, timing, label)
        _require(reader.read(), map_id, coordinate, label)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "celadon_arrived",
        "Reached Celadon Center",
    )
    _heal(actions, reader, emulator, timing)
    _checkpoint(records, progress, emulator, reader.read(), "celadon_ready", "Healed in Celadon")

    _move(actions, reader, emulator, CENTER_EXIT, timing, "Center exit")
    _move(actions, reader, emulator, CITY_TO_OUTER_TREE, timing, "outer tree")
    _cut(actions, reader, emulator, timing, "down", 0x2C, "outer Cut")
    _move(actions, reader, emulator, ("down",), timing, "outer crossing")
    _move(actions, reader, emulator, LOWER_CITY_TO_GYM, timing, "Gym door")
    _move(actions, reader, emulator, ("up",), timing, "Gym entry")
    _checkpoint(records, progress, emulator, reader.read(), "gym_entered", "Entered Celadon Gym")

    _move(actions, reader, emulator, ("up",) * 6, timing, "Lass trigger", allow_trigger=True)
    _enter_battle(actions, reader, timing, "Celadon Gym Lass")
    _require_identity(emulator, (0xCB, 0x03, 0xCB, 17), "Celadon Gym Lass")
    _battle(
        reader,
        actions,
        MapId.CELADON_GYM,
        timing,
        "Celadon Gym Lass",
        RedBattlePlanId.ERIKA_CELADON_GYM_LASS,
    )
    _checkpoint(records, progress, emulator, reader.read(), "lass_defeated", "Defeated Gym Lass")

    _move(actions, reader, emulator, _directions("UUUR"), timing, "inner tree")
    _cut(actions, reader, emulator, timing, "up", 0x2B, "inner Cut")
    _move(
        actions,
        reader,
        emulator,
        ("up", "up"),
        timing,
        "Cooltrainer trigger",
        allow_trigger=True,
    )
    _enter_battle(actions, reader, timing, "Celadon Gym Cooltrainer")
    _require_identity(emulator, (0xE8, 0x20, 0xE8, 1), "Celadon Gym Cooltrainer")
    _battle(
        reader,
        actions,
        MapId.CELADON_GYM,
        timing,
        "Celadon Gym Cooltrainer",
        RedBattlePlanId.ERIKA_CELADON_GYM_COOLTRAINER,
    )
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "cooltrainer_defeated",
        "Defeated required Gym Cooltrainer",
    )

    _cut(actions, reader, emulator, timing, "down", 0x2B, "inner re-Cut")
    _move(actions, reader, emulator, ("down",), timing, "inner re-cross")
    _move(actions, reader, emulator, GYM_EXIT, timing, "Gym recovery exit")
    _move(actions, reader, emulator, GYM_TO_OUTER_TREE_SOUTH, timing, "outer tree south")
    _cut(actions, reader, emulator, timing, "up", 0x2C, "outer re-Cut")
    _move(actions, reader, emulator, ("up",), timing, "outer re-cross")
    _move(actions, reader, emulator, OUTER_TREE_TO_CENTER, timing, "Center recovery")
    _heal(actions, reader, emulator, timing)
    _use_rare_candy_and_learn_skull_bash(actions, reader, emulator, timing)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "gym_recovered",
        "Recovered after trainers",
    )

    _move(actions, reader, emulator, CENTER_EXIT, timing, "Center exit two")
    _move(actions, reader, emulator, CITY_TO_OUTER_TREE, timing, "outer tree two")
    _cut(actions, reader, emulator, timing, "down", 0x2C, "outer Cut two")
    _move(actions, reader, emulator, ("down",), timing, "outer crossing two")
    _move(actions, reader, emulator, LOWER_CITY_TO_GYM, timing, "Gym door two")
    _move(actions, reader, emulator, ("up",), timing, "Gym entry two")
    _move(actions, reader, emulator, ("up",) * 9 + ("right",), timing, "inner tree two")
    _cut(actions, reader, emulator, timing, "up", 0x2B, "inner Cut two")
    _move(actions, reader, emulator, ("down",), timing, "reversible down")
    _move(actions, reader, emulator, ("up",), timing, "reversible up")
    _move(actions, reader, emulator, _directions("UULUU"), timing, "Erika stance")
    _require(reader.read(), MapId.CELADON_GYM, (4, 4), "Erika stance")
    _checkpoint(records, progress, emulator, reader.read(), "erika_stance", "Reached Erika")

    actions.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(actions, timing.movement_frames)
    _enter_battle(actions, reader, timing, "Erika")
    identity = _identity(emulator)
    _require_identity(emulator, (ERIKA_OPPONENT, ERIKA_CLASS, ERIKA_OPPONENT, 1), "Erika")
    _checkpoint(records, progress, emulator, reader.read(), "erika_battle", "Verified Erika")
    before_pp = reader.read().first_party_pp
    _battle(
        reader,
        actions,
        MapId.CELADON_GYM,
        timing,
        "Erika",
        RedBattlePlanId.ERIKA_LEADER,
    )
    after_pp = reader.read().first_party_pp
    if before_pp is None or after_pp is None:
        raise ErikaChapterError("Erika battle lacks PP evidence.")
    strength_spent = (before_pp[1] & 0x3F) - (after_pp[1] & 0x3F)
    _checkpoint(records, progress, emulator, reader.read(), "erika_defeated", "Defeated Erika")

    for _ in range(timing.dialogue_pulses):
        if (
            _event(emulator, EventFlag.BEAT_ERIKA)
            and _event(emulator, EventFlag.GOT_TM21)
            and emulator.read_u8(RamAddress.OBTAINED_BADGES) & int(Badge.RAINBOW)
            and _gym_events(emulator) == (True,) * 7
            and reader.read_input_readiness().ready
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    else:
        raise ErikaChapterError("Erika rewards did not settle.")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "rainbow_received",
        "Received Rainbow Badge",
    )

    # Leave through both regenerated trees and heal to the stable terminal.
    _move(actions, reader, emulator, _directions("DDR"), timing, "inner exit approach")
    _cut(actions, reader, emulator, timing, "down", 0x2B, "victory inner Cut")
    _move(actions, reader, emulator, ("down",), timing, "victory inner crossing")
    _move(actions, reader, emulator, GYM_EXIT, timing, "victory Gym exit")
    _move(actions, reader, emulator, GYM_TO_OUTER_TREE_SOUTH, timing, "victory outer tree")
    _cut(actions, reader, emulator, timing, "up", 0x2C, "victory outer Cut")
    _move(actions, reader, emulator, ("up",), timing, "victory outer crossing")
    _move(actions, reader, emulator, OUTER_TREE_TO_CENTER, timing, "victory Center")
    _heal(actions, reader, emulator, timing)
    final = reader.read()
    _checkpoint(records, progress, emulator, final, "erika_stable", "Healed Rainbow boundary")

    report = ErikaChapterReport(
        records=tuple(records),
        final_raw=final,
        erika_identity=identity,
        strength_pp_spent=strength_spent,
        moves_before=tuple(initial.first_party_moves or ()),
        moves_after=tuple(final.first_party_moves or ()),
        money_before=POST_KOGA_MONEY,
        money_after=_money(emulator),
        badge_bits=emulator.read_u8(RamAddress.OBTAINED_BADGES),
        beat_gym_flags=emulator.read_u8(RamAddress.BEAT_GYM_FLAGS),
        got_tm21=_event(emulator, EventFlag.GOT_TM21),
        beat_erika=_event(emulator, EventFlag.BEAT_ERIKA),
        gym_events_before=events_before,
        gym_events_after=_gym_events(emulator),
        optional_route_events_before=optional_events_before,
        optional_route_events_after=_optional_route_events(emulator),
        final_bag=tuple(sorted(_bag(emulator).items())),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise ErikaChapterError(f"Erika evidence contract failed: {report.public_dict()!r}.")
    return report


def _move(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    route: Iterable[str],
    timing: ErikaTiming,
    label: str,
    *,
    allow_trigger: bool = False,
) -> None:
    route = tuple(route)
    for index, direction in enumerate(route, 1):
        before = reader.read()
        for _ in range(timing.movement_retries):
            _pulse(actions, MacroActionKind.MOVE, direction, frames=timing.movement_frames)
            after = reader.read()
            if after.battle_state == 1:
                _flee(actions, reader, emulator, _RunState([]), DEFAULT_CELADON_TIMING)
                after = reader.read()
            if after.battle_state == 2:
                if allow_trigger and index == len(route):
                    return
                raise ErikaChapterError(f"Unexpected trainer during {label}.")
            if (after.map_id, after.player_x, after.player_y) != (
                before.map_id,
                before.player_x,
                before.player_y,
            ):
                break
            if allow_trigger and index == len(route):
                return
        else:
            raise ErikaChapterError(f"{label} blocked at step {index}/{len(route)}.")


def _cut(actions, reader, emulator, timing, facing, expected_tile, label) -> None:
    before = reader.read()
    _pulse(actions, MacroActionKind.MOVE, facing, frames=timing.movement_frames)
    after = reader.read()
    if (after.player_x, after.player_y) != (before.player_x, before.player_y):
        raise ErikaChapterError(f"{label} facing pulse moved unexpectedly.")
    actions.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(actions, timing.movement_frames)
    _select_menu(actions, emulator, 1, 6, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    _select_menu(actions, emulator, 1, 2, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    _select_menu(actions, emulator, 0, 3, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    for _ in range(timing.cut_pulses):
        if (
            emulator.read_u8(RamAddress.TILE_IN_FRONT_OF_PLAYER) == expected_tile
            and reader.read_input_readiness().ready
        ):
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    raise ErikaChapterError(f"{label} failed its tile/readiness gate.")


def _select_menu(actions, emulator, target, maximum, timing) -> None:
    for _ in range(maximum + 2):
        current = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if current == target:
            return
        down = (target - current) % (maximum + 1)
        up = (current - target) % (maximum + 1)
        _pulse(
            actions,
            MacroActionKind.MOVE,
            "down" if down <= up else "up",
            frames=timing.movement_frames,
        )
    raise ErikaChapterError("Menu cursor missed its semantic target.")


def _use_rare_candy_and_learn_skull_bash(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: ErikaTiming,
) -> None:
    before = reader.read()
    before_quantity = _bag(emulator).get(ItemId.RARE_CANDY, 0)
    if (
        before.first_party_level != 41
        or before.first_party_moves != (0x2C, STRENGTH, 0x3D, 0x39)
        or before_quantity != 1
    ):
        raise ErikaChapterError(
            "Rare Candy learning gate requires level 41, the qualified moves, "
            "and the source-qualified Tower candy: "
            f"level={before.first_party_level!r}, moves={before.first_party_moves!r}, "
            f"quantity={before_quantity}."
        )
    menu_timing = LavenderTiming(wait_frames=timing.movement_frames)
    _open_bag(actions, emulator, menu_timing)
    _select_bag_item(actions, emulator, ItemId.RARE_CANDY, menu_timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    for _ in range(timing.dialogue_pulses):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (0, 1):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    else:
        raise ErikaChapterError("Rare Candy did not reach party selection.")
    _select_cursor(actions, emulator, 0, menu_timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    for _ in range(80):
        raw = reader.read()
        if (
            raw.first_party_level == 42
            and raw.first_party_moves == (SKULL_BASH, STRENGTH, 0x3D, 0x39)
            and _bag(emulator).get(ItemId.RARE_CANDY, 0) == before_quantity - 1
        ):
            _close_menus(actions, reader, menu_timing)
            return
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (5, 8):
            _select_cursor(actions, emulator, 0, menu_timing)
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    raise ErikaChapterError("Rare Candy did not install Skull Bash in slot one.")


def _battle(reader, actions, map_id, timing, label, battle_plan_id: str) -> None:
    for _ in range(timing.battle_recoveries):
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                lambda _: 2,
                expected_map=int(map_id),
                intent=BattleIntent(
                    "defeat_erika",
                    battle_plan_id=battle_plan_id,
                    required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
                    required_move_ref=pokemon_red_move_ref(STRENGTH),
                ),
                required_move_id=STRENGTH,
                timing=BattleRuntimeTiming(
                    max_runtime_pulses=1600 if label == "Erika" else 960
                ),
                label=label,
                unknown_cancel_interval=3,
            )
            return
        except BattleRuntimeError:
            if reader.read().battle_state == 0:
                return
    raise ErikaChapterError(f"{label} exceeded bounded battle recoveries.")


def _enter_battle(actions, reader, timing, label) -> None:
    for _ in range(timing.dialogue_pulses):
        if reader.read().battle_state == 2:
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    raise ErikaChapterError(f"{label} did not enter battle.")


def _heal(actions, reader, emulator, timing) -> None:
    _require(reader.read(), MapId.CELADON_POKECENTER, (3, 7), "Celadon Center entry")
    _move(actions, reader, emulator, ("up",) * 4, timing, "Celadon nurse")
    for _ in range(9):
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    for _ in range(timing.heal_pulses):
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and _party_status(emulator) == (0, 0, 0)
            and reader.read_input_readiness().ready
        ):
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    raise ErikaChapterError("Celadon heal failed.")


def _event(emulator, event: EventFlag) -> bool:
    value = int(event)
    return bool(emulator.read_u8(int(RamAddress.EVENT_FLAGS) + value // 8) & (1 << value % 8))


def _gym_events(emulator) -> tuple[bool, ...]:
    return tuple(_event(emulator, event) for event in GYM_EVENTS)


def _optional_route_events(emulator) -> tuple[bool, ...]:
    return tuple(_event(emulator, event) for event in OPTIONAL_ROUTE_EVENTS)


def _identity(emulator) -> tuple[int, int, int, int]:
    return (
        emulator.read_u8(RamAddress.CURRENT_OPPONENT),
        emulator.read_u8(RamAddress.TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_SET),
    )


def _require_identity(emulator, expected, label) -> None:
    if _identity(emulator) != expected:
        raise ErikaChapterError(f"{label} identity mismatch: {_identity(emulator)!r}.")


def _require(raw, map_id, coordinate, label) -> None:
    if (
        raw.map_id != map_id
        or (raw.player_x, raw.player_y) != coordinate
        or raw.battle_state != 0
        or raw.party_species_ids != TOWER_FINAL_PARTY
    ):
        raise ErikaChapterError(
            f"{label} missed gate: map={raw.map_id}, "
            f"xy={(raw.player_x, raw.player_y)}, battle={raw.battle_state}."
        )


def _checkpoint(records, progress, emulator, raw, checkpoint_id, label) -> None:
    records.append(ErikaCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            ErikaProgress(
                checkpoint_id, label, len(records), ERIKA_CHECKPOINT_COUNT, emulator.frame_count
            )
        )


def _pulse(actions, kind, value=None, *, frames) -> None:
    actions.execute(MacroAction(kind, value))
    _wait(actions, frames)


def _wait(actions, frames) -> None:
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
