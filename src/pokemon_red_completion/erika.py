"""Qualified Fuchsia-to-Celadon traversal and Rainbow Badge chapter."""

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
    RequiredMovePolicy,
    run_adaptive_trainer_battle,
    run_adaptive_wild_battle,
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
from pokemon_red_completion.lavender import (
    LavenderTiming,
    _close_menus,
    _open_bag,
    _select_bag_item,
    _select_cursor,
)
from pokemon_red_completion.observation import (
    Badge,
    BattleMenuPhase,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.silph import (
    DEFAULT_SILPH_TIMING,
    ICE_BEAM_MOVE,
    SilphChapterError,
    _deposit_pc_item,
    acquire_and_teach_ice_beam_from_celadon_center,
)
from pokemon_red_completion.tower import party_core_intact

ERIKA_TRAINER_REWARD_TOTAL = 4_056
ERIKA_ICE_BEAM_PREPARATION_COST = 200

ERIKA_CHECKPOINT_COUNT = 12
STRENGTH = 0x46
ERIKA_OPPONENT = 0xED
ERIKA_CLASS = 0x25
SKULL_BASH = 0x82
BLASTOISE_SPECIES_ID = 0x1C
MOVEMENT_RETRY_WAIT_FRAMES = 12
GYM_EVENTS = tuple(
    EventFlag(int(EventFlag.BEAT_CELADON_GYM_TRAINER_0) + index) for index in range(7)
)
OPTIONAL_ROUTE_EVENTS = tuple(
    EventFlag(int(EventFlag.BEAT_ROUTE_14_TRAINER_0) + index) for index in range(10)
) + tuple(EventFlag(int(EventFlag.BEAT_ROUTE_15_TRAINER_0) + index) for index in range(10))
BATTLE_PARTY_MENU_COMMAND = 2
PARTY_SUBMENU_SWITCH = 0
BATTLE_COMMAND_COORDINATES = {
    0: (0, 0),
    1: (0, 1),
    2: (1, 0),
    3: (1, 1),
}


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
ROUTE_LEVEL_TRAINING_INTENT = BattleIntent(
    "train_party",
    battle_plan_id="red.route-15.level-training",
    resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
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
CENTER_EXIT_TWO = _directions("D")
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
    movement_retries: int = 16
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


@dataclass(slots=True)
class _RouteTrainingState:
    """Live receipt for the bounded level prerequisite taught on the route."""

    starting_level: int
    target_level: int
    battles_won: int = 0


@dataclass(frozen=True, slots=True)
class ErikaChapterReport:
    records: tuple[ErikaCheckpoint, ...]
    final_raw: RawGameState
    erika_identity: tuple[int, int, int, int]
    strength_pp_spent: int
    ice_beam_pp_spent: int
    got_tm13: bool
    tm13_transfer_before_event: bool
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
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool
    skull_bash_source: str = "tm40"
    route_training_start_level: int = 39
    route_training_target_level: int = 39
    route_training_final_level: int = 39
    route_training_battles: int = 0

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == ERIKA_CHECKPOINT_COUNT
            and self.erika_identity == (ERIKA_OPPONENT, ERIKA_CLASS, ERIKA_OPPONENT, 1)
            and 0 <= self.strength_pp_spent <= 10
            and 0 < self.ice_beam_pp_spent <= 10
            and self.got_tm13
            and self.tm13_transfer_before_event
            and (
                (
                    self.moves_before == (0x2C, STRENGTH, 0x3D, 0x39)
                    and self.skull_bash_source == "tm40"
                )
                or (
                    self.moves_before == (SKULL_BASH, STRENGTH, 0x3D, 0x39)
                    and self.skull_bash_source == "natural_level_42"
                )
            )
            and self.moves_after == (0x82, STRENGTH, ICE_BEAM_MOVE, 0x39)
            and self.money_before >= 0
            and self.money_after
            == self.money_before
            + ERIKA_TRAINER_REWARD_TOTAL
            - ERIKA_ICE_BEAM_PREPARATION_COST
            and self.badge_bits == 0x1F
            and self.beat_gym_flags & int(Badge.RAINBOW)
            and self.got_tm21
            and self.beat_erika
            and self.gym_events_before == (False,) * 7
            and self.gym_events_after == (True,) * 7
            and self.optional_route_events_before == (False,) * 20
            and self.optional_route_events_after == (False,) * 20
            and dict(self.final_bag).get(int(ItemId.TM21_MEGA_DRAIN)) == 1
            and int(ItemId.POKE_FLUTE) not in dict(self.final_bag)
            and int(ItemId.TM13_ICE_BEAM) not in dict(self.final_bag)
            and int(ItemId.FRESH_WATER) not in dict(self.final_bag)
            and int(ItemId.TM40_SKULL_BASH) not in dict(self.final_bag)
            and self.final_raw.map_id == MapId.CELADON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.final_raw.first_party_level is not None
            and 42 <= self.final_raw.first_party_level <= 43
            and self.final_raw.first_party_moves == (0x82, STRENGTH, ICE_BEAM_MOVE, 0x39)
            and self.final_raw.first_party_pp == (15, 15, 10, 15)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and self.final_raw.first_party_hp == self.party_hp[0]
            and self.final_raw.first_party_max_hp == self.party_max_hp[0]
            and all(status == 0 for status in self.party_status)
            and self.controller_released
            and self.route_training_start_level <= self.route_training_target_level
            and self.route_training_final_level >= self.route_training_target_level
            and self.route_training_battles >= 0
            and (
                self.route_training_battles > 0
                or self.route_training_start_level >= self.route_training_target_level
            )
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
                "ice_beam_move_id": ICE_BEAM_MOVE,
                "ice_beam_pp_spent": self.ice_beam_pp_spent,
                "ice_beam_preparation": {
                    "tm13_event": self.got_tm13,
                    "transfer_before_event": self.tm13_transfer_before_event,
                    "cost": ERIKA_ICE_BEAM_PREPARATION_COST,
                },
                "skull_bash_preparation": {
                    "source": (
                        "natural level-42 move; Safari TM40 archived"
                        if self.skull_bash_source == "natural_level_42"
                        else "Safari Zone North TM40"
                    ),
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
            "poke_flute_archived": int(ItemId.POKE_FLUTE) not in dict(self.final_bag),
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
            "route_training": {
                "starting_level": self.route_training_start_level,
                "target_level": self.route_training_target_level,
                "final_level": self.route_training_final_level,
                "battles_won": self.route_training_battles,
                "requirement_met": (
                    self.route_training_final_level >= self.route_training_target_level
                ),
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
    initial_moves = tuple(initial.first_party_moves or ())
    initial_pp = tuple(initial.first_party_pp or ())
    skull_bash_source = (
        "natural_level_42"
        if initial_moves == (SKULL_BASH, STRENGTH, 0x3D, 0x39)
        else "tm40"
    )
    if (
        _money(emulator) < 0
        or (initial_moves, initial_pp)
        not in {
            ((0x2C, STRENGTH, 0x3D, 0x39), (25, 15, 20, 15)),
            ((SKULL_BASH, STRENGTH, 0x3D, 0x39), (15, 15, 20, 15)),
        }
        or _event(emulator, EventFlag.BEAT_ERIKA)
        or ItemId.TM21_MEGA_DRAIN in _bag(emulator)
        or ItemId.TM13_ICE_BEAM in _bag(emulator)
        or _event(emulator, EventFlag.GOT_TM13)
    ):
        raise ErikaChapterError("Erika input boundary is not pristine.")
    money_before = _money(emulator)
    events_before = _gym_events(emulator)
    optional_events_before = _optional_route_events(emulator)
    if initial.first_party_level is None:
        raise ErikaChapterError("Route training lacks a live lead level.")
    if initial.first_party_level == 40 and _bag(emulator).get(ItemId.RARE_CANDY, 0) == 1:
        _use_route_training_rare_candy(actions, reader, emulator, timing)
        initial = reader.read()
    route_training = _RouteTrainingState(
        starting_level=initial.first_party_level,
        # Stop at the already-qualified level-41 training boundary. The Safari
        # lesson supplies TM40, avoiding an unsafe extra wild-grind cycle.
        target_level=max(initial.first_party_level, 41),
    )
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
        training_leg = route_training if label in {
            "fuchsia_exited",
            "route15_west",
            "route15_gate",
            "route15_east",
        } else None
        _move(
            actions,
            reader,
            emulator,
            route,
            timing,
            label,
            route_training=training_leg,
        )
        _require(reader.read(), map_id, coordinate, label)
        if label == "route15_east":
            _run_route15_training(
                actions,
                reader,
                emulator,
                timing,
                route_training,
            )
    route_training_final_level = reader.read().first_party_level
    if (
        route_training_final_level is None
        or route_training_final_level < route_training.target_level
    ):
        raise ErikaChapterError(
            "The bounded route-training lesson did not satisfy its level prerequisite: "
            f"start={route_training.starting_level}, "
            f"target={route_training.target_level}, "
            f"final={route_training_final_level!r}, "
            f"battles={route_training.battles_won}."
        )
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "celadon_arrived",
        "Reached Celadon Center",
    )
    _heal(actions, reader, emulator, timing)
    if _bag(emulator).get(ItemId.POKE_FLUTE, 0) != 1:
        raise ErikaChapterError("Celadon cleanup requires the spent Poké Flute.")
    _move(
        actions,
        reader,
        emulator,
        ("down",) + ("right",) * 10,
        timing,
        "Celadon PC approach",
    )
    try:
        _deposit_pc_item(
            actions,  # type: ignore[arg-type]
            reader,
            emulator,
            ItemId.POKE_FLUTE,
            DEFAULT_SILPH_TIMING,
        )
    except SilphChapterError as error:
        raise ErikaChapterError("Celadon Poké Flute cleanup failed.") from error
    if _bag(emulator).get(ItemId.RARE_CANDY, 0) == 1:
        try:
            _deposit_pc_item(
                actions,  # type: ignore[arg-type]
                reader,
                emulator,
                ItemId.RARE_CANDY,
                DEFAULT_SILPH_TIMING,
            )
        except SilphChapterError as error:
            raise ErikaChapterError("Celadon Rare Candy cleanup failed.") from error
    if ItemId.RARE_CANDY in _bag(emulator):
        raise ErikaChapterError("Celadon cleanup left the surplus Rare Candy in the bag.")
    if skull_bash_source == "natural_level_42":
        try:
            _deposit_pc_item(
                actions,  # type: ignore[arg-type]
                reader,
                emulator,
                ItemId.TM40_SKULL_BASH,
                DEFAULT_SILPH_TIMING,
            )
        except SilphChapterError as error:
            raise ErikaChapterError("Natural Skull Bash TM40 archival failed.") from error
        if ItemId.TM40_SKULL_BASH in _bag(emulator):
            raise ErikaChapterError("Natural Skull Bash lineage retained redundant TM40.")
    _move(
        actions,
        reader,
        emulator,
        ("left",) * 10 + ("up",),
        timing,
        "Celadon PC return",
    )
    _require(reader.read(), MapId.CELADON_POKECENTER, (3, 3), "Celadon PC return")
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
    if skull_bash_source == "tm40":
        _teach_tm40_skull_bash(actions, reader, emulator, timing)
    elif reader.read().first_party_moves != (SKULL_BASH, STRENGTH, 0x3D, 0x39):
        raise ErikaChapterError("Natural Skull Bash lineage changed before Gym recovery.")
    try:
        _, tm13_transfer_before_event = acquire_and_teach_ice_beam_from_celadon_center(
            actions,  # type: ignore[arg-type]
            reader,
            emulator,
        )
    except SilphChapterError as error:
        raise ErikaChapterError(f"Erika Ice Beam preparation failed: {error}") from error
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "gym_recovered",
        "Recovered after trainers",
    )

    _move(actions, reader, emulator, CENTER_EXIT_TWO, timing, "Center exit two")
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
    ice_beam_spent = (before_pp[2] & 0x3F) - (after_pp[2] & 0x3F)
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
        ice_beam_pp_spent=ice_beam_spent,
        got_tm13=_event(emulator, EventFlag.GOT_TM13),
        tm13_transfer_before_event=tm13_transfer_before_event,
        moves_before=tuple(initial.first_party_moves or ()),
        moves_after=tuple(final.first_party_moves or ()),
        money_before=money_before,
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
        skull_bash_source=skull_bash_source,
        route_training_start_level=route_training.starting_level,
        route_training_target_level=route_training.target_level,
        route_training_final_level=route_training_final_level,
        route_training_battles=route_training.battles_won,
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
    route_training: _RouteTrainingState | None = None,
) -> None:
    route = tuple(route)
    for index, direction in enumerate(route, 1):
        before = reader.read()
        for _ in range(timing.movement_retries):
            _pulse(actions, MacroActionKind.MOVE, direction, frames=timing.movement_frames)
            after = reader.read()
            if after.battle_state == 1:
                level = after.first_party_level
                if (
                    route_training is not None
                    and level is not None
                ):
                    battle_continues = True
                    if not _route_training_safe(after):
                        battle_continues = _switch_route_training_escort(
                            actions, reader, emulator
                        )
                    if battle_continues:
                        try:
                            run_adaptive_wild_battle(
                                reader,
                                actions,
                                _route_training_move_slot,
                                expected_map=int(after.map_id),
                                intent=ROUTE_LEVEL_TRAINING_INTENT,
                                label="bounded route level training",
                            )
                        except BattleRuntimeError as error:
                            raise ErikaChapterError(
                                f"Route training failed its bounded battle: {error}"
                            ) from error
                    route_training.battles_won += 1
                else:
                    _flee(actions, reader, emulator, _RunState([]), DEFAULT_CELADON_TIMING)
                after = reader.read()
            if after.battle_state == 2:
                if allow_trigger and index == len(route):
                    return
                raise ErikaChapterError(f"Unexpected trainer during {label}.")
            if (
                (after.map_id, after.player_x, after.player_y)
                == (before.map_id, before.player_x, before.player_y)
                and not reader.read_input_readiness().ready
            ):
                # Extra training changes when an earlier Repel expires.  Clear
                # that semantic field message instead of encoding its old step.
                _pulse(
                    actions,
                    MacroActionKind.CONFIRM,
                    frames=timing.movement_frames,
                )
                continue
            if (after.map_id, after.player_x, after.player_y) != (
                before.map_id,
                before.player_x,
                before.player_y,
            ):
                break
            if allow_trigger and index == len(route):
                return
            # Release the direction between attempts so moving overworld NPCs
            # can vacate a temporarily occupied route tile.
            _wait(actions, MOVEMENT_RETRY_WAIT_FRAMES * (_ + 1))
        else:
            current = reader.read()
            raise ErikaChapterError(
                f"{label} blocked at step {index}/{len(route)}: "
                f"direction={direction}, map={current.map_id!r}, "
                f"coordinate={(current.player_x, current.player_y)!r}."
            )


def _route_training_safe(raw: RawGameState) -> bool:
    """Require enough live health and attacking PP before choosing to train."""

    hp = raw.battler_hp
    maximum = raw.battler_max_hp
    moves = raw.battler_moves or ()
    pp = raw.battler_pp or ()
    attacking_slots = (4, 3, 1)
    return (
        hp is not None
        and maximum is not None
        and maximum > 0
        and hp / maximum >= 0.75
        and any(
            len(moves) >= slot
            and len(pp) >= slot
            and moves[slot - 1] != 0
            and pp[slot - 1] & 0x3F
            for slot in attacking_slots
        )
    )


def _route_training_move_slot(raw: RawGameState) -> int:
    """Prefer strong attacks while preserving Strength for field navigation."""

    moves = raw.battler_moves or ()
    pp = raw.battler_pp or ()
    if raw.enemy_species_id == BLASTOISE_SPECIES_ID:
        # Route 15 Ditto can transform into Blastoise.  Do not keep feeding
        # resisted Water attacks into the copy; use neutral Strength instead.
        ranking = (2, 1, 4, 3)
    else:
        ranking = (4, 3, 1, 2) if (raw.active_party_index or 0) == 0 else (1, 4, 3, 2)
    for slot in ranking:
        if (
            len(moves) >= slot
            and len(pp) >= slot
            and moves[slot - 1] != 0
            and pp[slot - 1] & 0x3F
            and raw.player_disabled_move_slot != slot
        ):
            return slot
    raise ErikaChapterError("Route training has no usable move.")


def _switch_route_training_escort(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
) -> bool:
    """Share experience with the healthiest reserve when the lead needs relief."""

    raw = reader.read()
    species = raw.party_species_ids or ()
    hp = _party_hp(emulator)
    maximum = _party_max_hp(emulator)
    status = _party_status(emulator)
    candidates = tuple(
        index
        for index in range(1, len(species))
        if hp[index] > 0
        and maximum[index] > 0
        and hp[index] / maximum[index] >= 0.45
        and status[index] == 0
    )
    if raw.battle_state != 1 or not candidates:
        raise ErikaChapterError(
            "Route training has no healthy reserve for safe shared experience."
        )
    # Absolute durability matters more than percentage here: the freshly
    # caught Snorlax is the qualified absorber, while Diglett can be at full
    # health and still be knocked out by one Route 15 attack.
    target_index = max(candidates, key=lambda index: (maximum[index], hp[index]))

    for pulse in range(48):
        raw = reader.read()
        menu = reader.read_battle_menu_state(raw)
        if raw.battle_state == 1 and menu.phase is BattleMenuPhase.MAIN:
            break
        if raw.battle_state == 0:
            raise ErikaChapterError("Route-training encounter ended before the safe switch.")
        _pulse(
            actions,
            MacroActionKind.CANCEL if (pulse + 1) % 4 == 0 else MacroActionKind.CONFIRM,
            frames=120,
        )
    else:
        raise ErikaChapterError("Route-training battle menu did not settle for a switch.")

    for pulse in range(16):
        menu = reader.read_battle_menu_state(reader.read())
        if (
            menu.phase is BattleMenuPhase.MAIN
            and menu.selected_main_command == BATTLE_PARTY_MENU_COMMAND
        ):
            break
        if menu.phase is not BattleMenuPhase.MAIN:
            _pulse(
                actions,
                MacroActionKind.CANCEL if (pulse + 1) % 4 == 0 else MacroActionKind.CONFIRM,
                frames=120,
            )
            continue
        direction = _battle_command_direction(
            menu.selected_main_command,
            BATTLE_PARTY_MENU_COMMAND,
        )
        if direction is None:
            raise ErikaChapterError("Route-training command cursor is invalid.")
        _pulse(actions, MacroActionKind.MOVE, direction, frames=120)
    else:
        raise ErikaChapterError("Route training could not select its healthy reserve.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)

    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target_index:
            break
        _pulse(
            actions,
            MacroActionKind.MOVE,
            "down" if cursor < target_index else "up",
            frames=120,
        )
    else:
        raise ErikaChapterError("Route training could not reach the reserve party slot.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    for _ in range(8):
        if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) == PARTY_SUBMENU_SWITCH:
            break
        _pulse(actions, MacroActionKind.MOVE, "up", frames=120)
    else:
        raise ErikaChapterError("Route training could not select SWITCH.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)

    for pulse in range(48):
        settled = reader.read()
        menu = reader.read_battle_menu_state(settled)
        if (
            settled.battle_state == 1
            and menu.phase is BattleMenuPhase.MAIN
            and emulator.read_u8(RamAddress.PLAYER_MON_NUMBER) == target_index
        ):
            return True
        if settled.battle_state == 0:
            for _ in range(48):
                if reader.read_input_readiness().ready:
                    return False
                _pulse(actions, MacroActionKind.CONFIRM, frames=120)
            raise ErikaChapterError(
                "Route-training battle ended during the reserve switch but field "
                "control did not settle."
            )
        _pulse(
            actions,
            MacroActionKind.CANCEL if (pulse + 1) % 4 == 0 else MacroActionKind.CONFIRM,
            frames=120,
        )
    raise ErikaChapterError("Route-training reserve switch did not settle.")


def _battle_command_direction(current: int | None, target: int) -> str | None:
    if current not in BATTLE_COMMAND_COORDINATES or target not in BATTLE_COMMAND_COORDINATES:
        return None
    current_x, current_y = BATTLE_COMMAND_COORDINATES[current]
    target_x, target_y = BATTLE_COMMAND_COORDINATES[target]
    if current_x != target_x:
        return "right" if current_x < target_x else "left"
    if current_y != target_y:
        return "down" if current_y < target_y else "up"
    return None


def _run_route15_training(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: ErikaTiming,
    training: _RouteTrainingState,
) -> None:
    """Seek encounters in a safe grass patch until the prerequisite is met.

    Route 15's gate exit is at ``(14, 9)``.  The unobstructed patch beginning at
    x=20 is clear of every optional trainer and lets the teacher alternate two
    grass tiles without encoding a particular encounter schedule.
    """

    _require(reader.read(), MapId.ROUTE_15, (14, 9), "Route 15 training origin")
    _move(
        actions,
        reader,
        emulator,
        ("right",) * 6,
        timing,
        "Route 15 training patch",
        route_training=training,
    )
    for step in range(512):
        level = reader.read().first_party_level
        if level is not None and level >= training.target_level:
            break
        _move(
            actions,
            reader,
            emulator,
            ("right" if step % 2 == 0 else "left",),
            timing,
            "Route 15 training search",
            route_training=training,
        )
    else:
        raise ErikaChapterError(
            "Route 15 training exhausted 512 bounded grass steps before meeting "
            f"level {training.target_level}."
        )

    raw = reader.read()
    if raw.map_id != MapId.ROUTE_15 or raw.player_x is None:
        raise ErikaChapterError("Route 15 training lost its field position.")
    if not 20 <= raw.player_x <= 21 or raw.player_y != 9:
        raise ErikaChapterError(
            "Route 15 training left its qualified grass pair: "
            f"{(raw.player_x, raw.player_y)!r}."
        )
    _move(
        actions,
        reader,
        emulator,
        ("left",) * (raw.player_x - 14),
        timing,
        "Route 15 training return",
        route_training=training,
    )
    _require(reader.read(), MapId.ROUTE_15, (14, 9), "Route 15 training return")


def _teach_tm40_skull_bash(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: ErikaTiming,
) -> None:
    before = reader.read()
    if (
        before.first_party_level is None
        or before.first_party_level < 41
        or before.first_party_moves != (0x2C, STRENGTH, 0x3D, 0x39)
        or _bag(emulator).get(ItemId.TM40_SKULL_BASH, 0) != 1
        or ItemId.RARE_CANDY in _bag(emulator)
    ):
        raise ErikaChapterError(
            "TM40 Skull Bash lesson lacks its qualified boundary: "
            f"level={before.first_party_level!r}, moves={before.first_party_moves!r}, "
            f"tm40={_bag(emulator).get(ItemId.TM40_SKULL_BASH, 0)}, "
            f"rare_candy={_bag(emulator).get(ItemId.RARE_CANDY, 0)}."
        )

    menu_timing = LavenderTiming(wait_frames=timing.movement_frames)
    _open_bag(actions, emulator, menu_timing)  # type: ignore[arg-type]
    _select_bag_item(  # type: ignore[arg-type]
        actions, emulator, ItemId.TM40_SKULL_BASH, menu_timing
    )
    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (0, 1):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    else:
        raise ErikaChapterError("TM40 did not reach party selection.")
    _select_cursor(actions, emulator, 0, menu_timing)  # type: ignore[arg-type]
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (5, 8):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    else:
        raise ErikaChapterError("TM40 did not reach move deletion.")
    _select_cursor(actions, emulator, 0, menu_timing)  # type: ignore[arg-type]
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    for _ in range(24):
        raw = reader.read()
        if raw.first_party_moves == (
            SKULL_BASH,
            STRENGTH,
            0x3D,
            0x39,
        ) and ItemId.TM40_SKULL_BASH not in _bag(emulator):
            _close_menus(actions, reader, menu_timing)  # type: ignore[arg-type]
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    raise ErikaChapterError("TM40 did not replace Bite and consume the TM.")


def _use_route_training_rare_candy(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: ErikaTiming,
) -> None:
    """Use a surplus Tower candy for the level-41 curriculum boundary."""

    before = reader.read()
    before_moves = before.first_party_moves
    if (
        before.first_party_level != 40
        or before_moves != (0x2C, STRENGTH, 0x3D, 0x39)
        or _bag(emulator).get(ItemId.RARE_CANDY, 0) != 1
        or not reader.read_input_readiness().ready
    ):
        raise ErikaChapterError(
            "Route-training Rare Candy lacks its level-40 field boundary."
        )

    menu_timing = LavenderTiming(wait_frames=timing.movement_frames)
    _open_bag(actions, emulator, menu_timing)  # type: ignore[arg-type]
    _select_bag_item(  # type: ignore[arg-type]
        actions, emulator, ItemId.RARE_CANDY, menu_timing
    )
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    for _ in range(timing.dialogue_pulses):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (0, 1):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    else:
        raise ErikaChapterError("Route-training Rare Candy did not reach party selection.")
    _select_cursor(actions, emulator, 0, menu_timing)  # type: ignore[arg-type]
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    for _ in range(64):
        current = reader.read()
        if (
            current.first_party_level == 41
            and current.first_party_moves == before_moves
            and _bag(emulator).get(ItemId.RARE_CANDY, 0) == 0
        ):
            _close_menus(actions, reader, menu_timing)  # type: ignore[arg-type]
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.movement_frames)
    raise ErikaChapterError("Route-training Rare Candy did not establish level 41.")


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


def _battle(reader, actions, map_id, timing, label, battle_plan_id: str) -> None:
    last_error: BattleRuntimeError | None = None
    for _ in range(timing.battle_recoveries):
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                _erika_move_slot,
                expected_map=int(map_id),
                intent=BattleIntent(
                    "defeat_erika",
                    battle_plan_id=battle_plan_id,
                    required_move_policy=RequiredMovePolicy.ANY_USABLE,
                    required_move_ref=None,
                ),
                required_move_id=None,
                timing=BattleRuntimeTiming(
                    max_runtime_pulses=1600 if label == "Erika" else 960
                ),
                label=label,
                unknown_cancel_interval=3,
            )
            return
        except BattleRuntimeError as error:
            last_error = error
            if reader.read().battle_state == 0:
                return
    raise ErikaChapterError(
        f"{label} exceeded bounded battle recoveries: {last_error}."
    )


def _erika_move_slot(raw: RawGameState) -> int:
    moves = raw.first_party_moves
    pp = raw.first_party_pp
    if moves is None or pp is None:
        raise ErikaChapterError("Erika battle lacks live move and PP evidence.")
    ranking = (3, 2, 1, 4) if len(moves) > 2 and moves[2] == ICE_BEAM_MOVE else (2, 1, 4, 3)
    for slot in ranking:
        index = slot - 1
        if (
            len(moves) > index
            and len(pp) > index
            and moves[index] != 0
            and pp[index] & 0x3F
            and raw.player_disabled_move_slot != slot
        ):
            return slot
    raise ErikaChapterError("Erika battle has no usable ranked move.")


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
            and all(status == 0 for status in _party_status(emulator))
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
        or not party_core_intact(raw.party_species_ids)
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
