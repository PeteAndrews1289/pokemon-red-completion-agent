"""Deterministic post-Brock chapter through a verified Cerulean arrival.

The route and semantic gates are pinned to pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8``. The chapter continues the same
clean run used to qualify Brock. It never saves, restores, or reads revision
specific memory directly; all gates come from the observation adapter.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.economy import (
    CERULEAN_RIVAL_POTION_RESERVE,
    PEWTER_LOSS_POTION_PURCHASE_QUANTITY,
    PEWTER_POKE_BALL_PRICE,
    PEWTER_POTION_PRICE,
    PEWTER_POTION_PURCHASE_QUANTITY,
    PEWTER_SUPPLY_LOSS_STARTING_MONEY,
    PEWTER_SUPPLY_STARTING_MONEY,
)
from pokemon_red_completion.observation import (
    BUBBLE_MOVE_ID,
    MEGA_PUNCH_MOVE_ID,
    ROUTE_3_REQUIRED_TRAINER_SPECS,
    SQUIRTLE_SPECIES_ID,
    WARTORTLE_SPECIES_ID,
    ZUBAT_SPECIES_ID,
    BattleMenuPhase,
    CeruleanBoundary,
    CeruleanChapterState,
    CeruleanPhase,
    CeruleanProgressError,
    CeruleanProgressTracker,
    ItemId,
    MapId,
    PewterChapterState,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.route_1_wild import (
    Route1WildFleeEvidence,
    flee_wild,
    move_with_wild_flees,
)

CERULEAN_CHECKPOINT_COUNT = 15
ROUTE_3_REQUIRED_TRAINER_INDEXES = tuple(spec[0] for spec in ROUTE_3_REQUIRED_TRAINER_SPECS)
ROUTE_3_BUBBLE_TRAINER_INDEXES = frozenset({0, 3, 6})
CERULEAN_QUALIFICATION_BOUNDARIES = tuple(
    boundary for boundary in CeruleanBoundary if boundary is not CeruleanBoundary.UNKNOWN
)


def _directions(compact: str) -> tuple[str, ...]:
    lookup = {"U": "up", "D": "down", "L": "left", "R": "right"}
    return tuple(lookup[direction] for direction in compact)


GYM_EXIT_APPROACH_DIRECTIONS = _directions("D" + "L" * 3 + "D" * 4 + "R" * 3 + "D" * 5)
GYM_EXIT_TRANSITION_DIRECTIONS = ("down",)
PEWTER_TO_CENTER_DIRECTIONS = _directions(
    "L" * 6 + "U" * 2 + "R" + "U" * 3 + "R" * 8 + "D" * 13 + "L" * 6 + "U"
)
PEWTER_TO_MART_PREFIX_DIRECTIONS = _directions(
    "L" * 6 + "U" * 2 + "R" + "U" * 3 + "R" * 8
)
PEWTER_MART_ENTRY_DIRECTIONS = _directions("D" * 5 + "R" * 4 + "U")
PEWTER_MART_CLERK_DIRECTIONS = _directions("UUL")
PEWTER_MART_EXIT_DIRECTIONS = _directions("RDDD")
PEWTER_MART_TO_CENTER_DIRECTIONS = _directions("L" * 4 + "D" * 8 + "L" * 6 + "U")
CENTER_HEAL_APPROACH_DIRECTIONS = ("up",) * 4
CENTER_EXIT_DIRECTIONS = ("down",) * 5
CENTER_HEAL_TO_PC_DIRECTIONS = ("down",) + ("right",) * 10
CENTER_PC_TO_HEAL_DIRECTIONS = ("left",) * 10 + ("up",)
FIELD_ITEM_MENU_CLOSE_PULSES = 4
ROUTE_3_BATTLE_RECOVERY_HP = 13
ROUTE_3_PROTECTED_POTION_FLOOR = 12
ROUTE_3_MAX_WILD_FLEES = 4
ROUTE_3_MAX_STEP_ATTEMPTS = 8
ROUTE_3_STEP_RETRY_WAIT_FRAMES = 24
ROUTE_3_WILD_STABILIZATION_FRAMES = 120
MT_MOON_ZUBAT_SEARCH_CYCLES = 64
MT_MOON_ZUBAT_SEARCH_MAX_FLEES = 32
MT_MOON_MAX_WILD_FLEES = 64
CENTER_TO_ROUTE_3_DIRECTIONS = _directions("R" * 3 + "U" * 4 + "R" * 3 + "U" * 4 + "R" * 21)
ROUTE_3_TO_PEWTER_CENTER_DIRECTIONS = _directions(
    "L" * 20 + "D" * 4 + "L" * 3 + "D" * 4 + "L" * 3 + "U"
)
ROUTE_3_TRAINER_SEGMENTS = tuple(
    _directions(segment)
    for segment in (
        "R" * 8 + "U" + "R" * 3 + "U" * 3,
        "R" * 3,
        "R" * 2 + "U" + "R" * 2 + "D" + "R",
        "R" * 3 + "U" + "R" * 3 + "D",
    )
)
ROUTE_3_REMAINDER_DIRECTIONS = _directions(
    "R" * 2
    + "D" * 5
    + "R" * 10
    + "U" * 6
    + "R" * 7
    + "D"
    + "R" * 5
    + "D" * 4
    + "R" * 8
    + "U" * 2
    + "R" * 2
    + "U" * 8
)
ROUTE_3_TO_ROUTE_4_DIRECTIONS = ("up",)
ROUTE_4_TO_MT_MOON_CENTER_DIRECTIONS = _directions(
    "U" + "R" + "U" * 5 + "R" * 2 + "U" * 6 + "L" + "U"
)
MT_MOON_CENTER_TO_1F_DIRECTIONS = _directions("R" * 7 + "U")

MT_MOON_1F_DIRECTIONS = _directions(
    "U" * 13
    + "R" * 6
    + "U" * 12
    + "R" * 10
    + "U"
    + "R"
    + "U" * 6
    + "L" * 15
    + "D" * 12
    + "R"
    + "D" * 2
    + "L" * 11
    + "U" * 12
    + "L"
)
MT_MOON_1F_PRE_TM_SEED_WAITS = ((1, 220), (10, 2), (30, 1), (31, 1))
MT_MOON_1F_POST_TM_SEED_WAITS = ((6, 2), (28, 2))
MT_MOON_POTION_DETOUR_ORIGIN = (31, 9)
MT_MOON_POTION_APPROACH_DIRECTIONS = _directions("R" * 3 + "D" * 24 + "L" * 13)
MT_MOON_POTION_RETURN_DIRECTIONS = _directions("R" * 13 + "U" * 24 + "L" * 3)
MT_MOON_POTION_PICKUP_POSITION = (21, 33)
MT_MOON_POTION_TOGGLE_INDEX = 0x6B
MT_MOON_SUPER_NERD_RECOVERY_HP = 25
MT_MOON_B1F_DIRECTIONS = _directions("R" * 2 + "D" * 11 + "R" * 14 + "D")
MT_MOON_B1F_SEED_WAITS = ((1, 2), (14, 1))
MT_MOON_B2F_TO_ROCKET_DIRECTIONS = _directions(
    "U" * 3
    + "R" * 5
    + "D" * 2
    + "R" * 6
    + "U" * 2
    + "R" * 4
    + "D" * 10
    + "L" * 2
    + "D" * 7
    + "L" * 23
    + "U" * 11
)
MT_MOON_B2F_SEED_WAITS = ((1, 9), (19, 1), (29, 2), (65, 2))
ROCKET_TRIGGER_DIRECTIONS = ("up",)
ROCKET_TO_SUPER_NERD_DIRECTIONS = _directions("L" + "U" * 3 + "R" * 2 + "U" * 7 + "R" + "U")
SUPER_NERD_TO_HELIX_DIRECTIONS = ("up",)
MT_MOON_B2F_EXIT_DIRECTIONS = _directions("U" * 3 + "L" * 10 + "D" * 2 + "R" * 2 + "D")
MT_MOON_B2F_EXIT_SEED_WAIT = 1
MT_MOON_B1F_EXIT_DIRECTIONS = ("right",) * 4
MT_MOON_B1F_EXIT_SEED_WAIT = 1
ROUTE_3_REJOIN_SEED_WAIT = 8
MT_MOON_ZUBAT_SEED_WAIT = 155
MT_MOON_ZUBAT_PRE_THROW_WAIT = 3

ROUTE_4_FIRST_LEDGE_APPROACH_DIRECTIONS = ("right",) * 20
ROUTE_4_FIRST_LEDGE_DIRECTIONS = ("right",)
ROUTE_4_MIDDLE_DIRECTIONS = _directions("R" * 3 + "D" * 4 + "R" * 12 + "U" * 2 + "R" * 18)
ROUTE_4_SECOND_LEDGE_DIRECTIONS = ("down",)
ROUTE_4_FINAL_APPROACH_DIRECTIONS = ("right",) * 10
ROUTE_4_TO_CERULEAN_DIRECTIONS = ("right",)


class CeruleanChapterError(RuntimeError):
    """Raised when the bounded Brock-to-Cerulean chapter misses a gate."""


class ActionExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class EmulatorState(Protocol):
    frame_count: int

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


@dataclass(frozen=True, slots=True)
class CeruleanTiming:
    transition_wait_frames: int = 120
    dialogue_wait_frames: int = 240
    battle_wait_frames: int = 180
    fight_menu_wait_frames: int = 120
    move_cursor_wait_frames: int = 120
    selected_move_wait_frames: int = 180
    super_nerd_preselect_wait_frames: int = 1
    b1f_exit_seed_wait_frames: int = 2
    final_stability_wait_frames: int = 1
    heal_dialogue_pulses: int = 9
    rocket_cleanup_pulses: int = 2
    fossil_dialogue_pulses: int = 4
    max_trainer_intro_pulses: int = 12
    max_main_menu_pulses: int = 12
    max_move_cursor_pulses: int = 5
    max_attack_start_pulses: int = 6
    max_battle_pulses: int = 180

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_CERULEAN_TIMING = CeruleanTiming()


@dataclass(frozen=True, slots=True)
class CeruleanProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[CeruleanProgress], None]


@dataclass(frozen=True, slots=True)
class CeruleanChapterReport:
    starting_brock_evidence: PewterChapterState
    route_3_reached: RawGameState
    route_3_battles: tuple[RawGameState, ...]
    route_3_victories: tuple[RawGameState, ...]
    route_4_reached: RawGameState
    mt_moon_entered: RawGameState
    mt_moon_b1f_reached: RawGameState
    mt_moon_b2f_reached: RawGameState
    rocket_battle: RawGameState
    rocket_defeated: RawGameState
    super_nerd_battle: RawGameState
    super_nerd_defeated: RawGameState
    fossil_obtained: RawGameState
    mt_moon_b1f_ascent: RawGameState
    mt_moon_exited: RawGameState
    cerulean_reached: RawGameState
    route_3_battle_evidence: tuple[CeruleanChapterState, ...]
    route_3_victory_evidence: tuple[CeruleanChapterState, ...]
    route_3_wild_flees: tuple[Route1WildFleeEvidence, ...]
    route_3_movement_retries: int
    mt_moon_zubat_search_flees: tuple[Route1WildFleeEvidence, ...]
    mt_moon_zubat_search_attempts: int
    mt_moon_zubat_movement_retries: int
    mt_moon_wild_flees: tuple[Route1WildFleeEvidence, ...]
    mt_moon_movement_retries: int
    rocket_battle_evidence: CeruleanChapterState
    rocket_victory_evidence: CeruleanChapterState
    super_nerd_battle_evidence: CeruleanChapterState
    super_nerd_victory_evidence: CeruleanChapterState
    fossil_evidence: CeruleanChapterState
    cerulean_evidence: CeruleanChapterState
    reached_boundaries: tuple[CeruleanBoundary, ...]
    observed_route_3_trainers: tuple[int, ...]
    saw_required_rocket_battle: bool
    saw_super_nerd_battle: bool
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            self.starting_brock_evidence.brock_victory_snapshot
            and self.reached_boundaries == CERULEAN_QUALIFICATION_BOUNDARIES
            and self.observed_route_3_trainers == ROUTE_3_REQUIRED_TRAINER_INDEXES
            and len(self.route_3_battle_evidence) == len(ROUTE_3_REQUIRED_TRAINER_INDEXES)
            and all(state.route_3_trainer_battle_snapshot for state in self.route_3_battle_evidence)
            and _route_3_victory_sequence(self.route_3_victory_evidence)
            and all(evidence.verified for evidence in self.route_3_wild_flees)
            and self.route_3_movement_retries >= 0
            and all(evidence.verified for evidence in self.mt_moon_zubat_search_flees)
            and 1 <= self.mt_moon_zubat_search_attempts <= MT_MOON_ZUBAT_SEARCH_CYCLES
            and self.mt_moon_zubat_movement_retries >= 0
            and all(evidence.verified for evidence in self.mt_moon_wild_flees)
            and len(self.mt_moon_wild_flees) <= MT_MOON_MAX_WILD_FLEES
            and len(self.mt_moon_wild_flees) >= len(self.mt_moon_zubat_search_flees)
            and all(
                evidence in self.mt_moon_wild_flees
                for evidence in self.mt_moon_zubat_search_flees
            )
            and self.mt_moon_movement_retries >= self.mt_moon_zubat_movement_retries
            and self.saw_required_rocket_battle
            and self.rocket_battle_evidence.required_rocket_battle_snapshot
            and self.rocket_battle.first_party_moves is not None
            and len(self.rocket_battle.first_party_moves) >= 3
            and self.rocket_battle.first_party_moves[2] == MEGA_PUNCH_MOVE_ID
            and self.rocket_victory_evidence.beat_required_rocket
            and self.saw_super_nerd_battle
            and self.super_nerd_battle_evidence.super_nerd_battle_snapshot
            and self.super_nerd_victory_evidence.beat_super_nerd
            and self.fossil_evidence.fossil_snapshot
            and self.fossil_evidence.got_helix_fossil
            and self.fossil_evidence.helix_fossil_in_bag
            and not self.fossil_evidence.got_dome_fossil
            and not self.fossil_evidence.dome_fossil_in_bag
            and self.cerulean_evidence.cerulean_snapshot
            and self.cerulean_reached.first_party_status == 0
            and (self.cerulean_reached.first_party_hp or 0) > 0
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        trainer_checkpoints = tuple(
            (
                f"route_3_trainer_{trainer_index}",
                f"Verified required Route 3 trainer {trainer_index}",
                raw,
            )
            for trainer_index, raw in zip(
                ROUTE_3_REQUIRED_TRAINER_INDEXES,
                self.route_3_battles,
                strict=True,
            )
        )
        return (
            ("route_3_reached", "Reached Route 3 from Pewter", self.route_3_reached),
            *trainer_checkpoints,
            ("route_4_reached", "Cleared the required Route 3 trainers", self.route_4_reached),
            ("mt_moon_entered", "Entered Mt. Moon", self.mt_moon_entered),
            ("mt_moon_b1f", "Reached the connected Mt. Moon B1F route", self.mt_moon_b1f_reached),
            ("mt_moon_b2f", "Reached the fossil-side Mt. Moon B2F route", self.mt_moon_b2f_reached),
            ("required_rocket", "Verified the unavoidable Team Rocket battle", self.rocket_battle),
            (
                "super_nerd",
                "Verified the fossil-guarding Super Nerd battle",
                self.super_nerd_battle,
            ),
            ("helix_fossil", "Obtained the Helix Fossil", self.fossil_obtained),
            (
                "mt_moon_b1f_ascent",
                "Reached the legal Mt. Moon exit ladder",
                self.mt_moon_b1f_ascent,
            ),
            ("mt_moon_exited", "Exited Mt. Moon onto Route 4", self.mt_moon_exited),
            ("cerulean_reached", "Reached Cerulean City", self.cerulean_reached),
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "checkpoints": [
                {
                    "id": checkpoint_id,
                    "label": label,
                    "status": "verified",
                    "state": _public_state(state),
                }
                for checkpoint_id, label, state in self.checkpoints()
            ],
            "route": {
                "ordered_boundaries_verified": len(self.reached_boundaries),
                "ordered_boundaries_total": len(CERULEAN_QUALIFICATION_BOUNDARIES),
                "required_route_3_trainers": list(self.observed_route_3_trainers),
                "route_3_wild_flees": [
                    evidence.public_dict() for evidence in self.route_3_wild_flees
                ],
                "route_3_movement_retries": self.route_3_movement_retries,
            },
            "mt_moon": {
                "required_rocket_battle_observed": self.saw_required_rocket_battle,
                "mega_punch_taught_before_rocket": (
                    self.rocket_battle.first_party_moves is not None
                    and len(self.rocket_battle.first_party_moves) >= 3
                    and self.rocket_battle.first_party_moves[2] == MEGA_PUNCH_MOVE_ID
                ),
                "super_nerd_battle_observed": self.saw_super_nerd_battle,
                "helix_fossil_verified": self.fossil_evidence.fossil_snapshot
                and self.fossil_evidence.got_helix_fossil,
                "zubat_search_attempts": self.mt_moon_zubat_search_attempts,
                "zubat_movement_retries": self.mt_moon_zubat_movement_retries,
                "zubat_search_flees": [
                    evidence.public_dict() for evidence in self.mt_moon_zubat_search_flees
                ],
                "wild_flees": [evidence.public_dict() for evidence in self.mt_moon_wild_flees],
                "movement_retries": self.mt_moon_movement_retries,
            },
            "cerulean": {
                "arrival_verified": self.cerulean_evidence.cerulean_snapshot,
                "wartortle_level": self.cerulean_reached.first_party_level,
                "wartortle_hp": self.cerulean_reached.first_party_hp,
                "wartortle_max_hp": self.cerulean_reached.first_party_max_hp,
                "wartortle_status": self.cerulean_reached.first_party_status,
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


class _CountingChapterExecutor:
    def __init__(self, executor: ActionExecutor) -> None:
        self._executor = executor
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> object:
        result = self._executor.execute(action)
        self.actions_executed += 1
        return result


@dataclass(slots=True)
class _MtMoonTraversalLedger:
    """One cumulative evidence budget for every incidental cave encounter."""

    flees: list[Route1WildFleeEvidence] = field(default_factory=list)
    movement_retries: int = 0

    @property
    def remaining_flees(self) -> int:
        return MT_MOON_MAX_WILD_FLEES - len(self.flees)


def run_cerulean_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ActionExecutor,
    *,
    timing: CeruleanTiming = DEFAULT_CERULEAN_TIMING,
    progress: ProgressSink | None = None,
) -> CeruleanChapterReport:
    """Continue one clean run from the verified Brock gate to Cerulean City."""
    start_frames = emulator.frame_count
    chapter_executor = _CountingChapterExecutor(executor)
    starting_raw = reader.read()
    starting_brock_evidence = reader.read_pewter_chapter_state(starting_raw)
    if (
        starting_raw.map_id != MapId.PEWTER_GYM
        or starting_raw.player_x != 4
        or starting_raw.player_y != 3
    ):
        raise CeruleanChapterError(
            "Cerulean qualification must start at the restored post-Brock control tile."
        )
    try:
        tracker = CeruleanProgressTracker(starting_brock_evidence)
    except CeruleanProgressError as error:
        raise CeruleanChapterError(str(error)) from error

    _move(chapter_executor, reader, GYM_EXIT_APPROACH_DIRECTIONS, "Pewter Gym exit")
    _move(
        chapter_executor,
        reader,
        GYM_EXIT_TRANSITION_DIRECTIONS,
        "Pewter Gym door",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _expect_position(reader.read(), MapId.PEWTER_CITY, 16, 18, "Pewter Gym exterior")

    _move(
        chapter_executor,
        reader,
        PEWTER_TO_MART_PREFIX_DIRECTIONS,
        "Pewter supply-route prefix",
    )
    _move(
        chapter_executor,
        reader,
        PEWTER_MART_ENTRY_DIRECTIONS,
        "Pewter Mart entry",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _purchase_early_supplies(chapter_executor, reader, emulator, timing)
    _leave_pewter_mart(chapter_executor, reader, timing)
    _move(
        chapter_executor,
        reader,
        PEWTER_MART_TO_CENTER_DIRECTIONS,
        "Pewter Mart to Center",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _expect_position(reader.read(), MapId.PEWTER_POKECENTER, 3, 7, "Pewter Center")
    _heal(
        chapter_executor,
        reader,
        timing,
        MapId.PEWTER_POKECENTER,
        "Pewter Center",
        emulator=emulator,
        withdraw_pc_potion=True,
    )
    _wait(chapter_executor, ROUTE_3_REJOIN_SEED_WAIT)

    _move(chapter_executor, reader, CENTER_TO_ROUTE_3_DIRECTIONS, "Route 3 entry")
    _wait(chapter_executor, timing.transition_wait_frames)
    route_3_reached, _ = _observe_boundary(
        reader,
        tracker,
        CeruleanBoundary.ROUTE_3_WEST_ENTRY,
    )
    _emit(progress, emulator, "route_3_reached", "Reached Route 3 from Pewter", 1)

    route_3_battles: list[RawGameState] = []
    route_3_victories: list[RawGameState] = []
    route_3_battle_evidence: list[CeruleanChapterState] = []
    route_3_victory_evidence: list[CeruleanChapterState] = []
    route_prefix: tuple[str, ...] = ()
    for position, (trainer_index, segment) in enumerate(
        zip(
            ROUTE_3_REQUIRED_TRAINER_INDEXES,
            ROUTE_3_TRAINER_SEGMENTS,
            strict=True,
        )
    ):
        _move(
            chapter_executor,
            reader,
            segment,
            f"Route 3 trainer {trainer_index} approach",
        )
        route_prefix += segment
        battle = _enter_trainer_battle(
            chapter_executor,
            reader,
            timing,
            MapId.ROUTE_3,
            f"Route 3 trainer {trainer_index}",
        )
        battle_evidence = reader.read_cerulean_chapter_state(battle)
        _observe_semantic(
            tracker,
            battle_evidence,
            CeruleanPhase.ROUTE_3_TRAINER_BATTLE,
            f"Route 3 trainer {trainer_index}",
        )
        if battle_evidence.route_3_trainer_battle_index != trainer_index:
            raise CeruleanChapterError(
                f"Route 3 trainer {trainer_index} failed its exact identity gate."
            )
        route_3_battles.append(battle)
        route_3_battle_evidence.append(battle_evidence)
        _select_battle_move(
            chapter_executor,
            reader,
            timing,
            slot=3 if trainer_index in ROUTE_3_BUBBLE_TRAINER_INDEXES else 1,
            label=f"Route 3 trainer {trainer_index}",
        )
        victory = _finish_battle(
            chapter_executor,
            reader,
            timing,
            MapId.ROUTE_3,
            f"Route 3 trainer {trainer_index}",
            emulator=emulator if position == 1 else None,
            recovery_hp_threshold=(
                ROUTE_3_BATTLE_RECOVERY_HP if position == 1 else None
            ),
            recovery_potion_floor=ROUTE_3_PROTECTED_POTION_FLOOR,
        )
        victory_evidence = reader.read_cerulean_chapter_state(victory)
        _expect_route_3_victory(victory_evidence, position)
        route_3_victories.append(victory)
        route_3_victory_evidence.append(victory_evidence)
        _emit(
            progress,
            emulator,
            f"route_3_trainer_{trainer_index}",
            f"Verified required Route 3 trainer {trainer_index}",
            position + 2,
        )
        if position == 0:
            _use_route_3_recovery_potion(
                chapter_executor,
                reader,
                emulator,
                timing,
            )
        _recover_at_pewter_center(
            chapter_executor,
            reader,
            timing,
            route_prefix,
        )

    _, route_3_wild_flees, route_3_movement_retries = move_with_wild_flees(
        chapter_executor,
        reader,
        ROUTE_3_REMAINDER_DIRECTIONS,
        "Route 3 east route",
        expected_map_id=MapId.ROUTE_3,
        route_name="Route 3",
        maximum_flees=ROUTE_3_MAX_WILD_FLEES,
        stabilization_frames=ROUTE_3_WILD_STABILIZATION_FRAMES,
        maximum_step_attempts=ROUTE_3_MAX_STEP_ATTEMPTS,
        step_retry_wait_frames=ROUTE_3_STEP_RETRY_WAIT_FRAMES,
        error_type=CeruleanChapterError,
    )
    _move(
        chapter_executor,
        reader,
        ROUTE_3_TO_ROUTE_4_DIRECTIONS,
        "Route 4 transition",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    route_4_reached, _ = _observe_boundary(
        reader,
        tracker,
        CeruleanBoundary.ROUTE_4_WEST_ENTRY,
    )
    _emit(
        progress,
        emulator,
        "route_4_reached",
        "Cleared the required Route 3 trainers",
        6,
    )

    _move(
        chapter_executor,
        reader,
        ROUTE_4_TO_MT_MOON_CENTER_DIRECTIONS,
        "Mt. Moon Center route",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _expect_position(
        reader.read(),
        MapId.MT_MOON_POKECENTER,
        3,
        7,
        "Mt. Moon Center",
    )
    _heal(
        chapter_executor,
        reader,
        timing,
        MapId.MT_MOON_POKECENTER,
        "Mt. Moon Center",
    )
    _move(
        chapter_executor,
        reader,
        MT_MOON_CENTER_TO_1F_DIRECTIONS,
        "Mt. Moon entrance",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    mt_moon_entered, _ = _observe_boundary(
        reader,
        tracker,
        CeruleanBoundary.MT_MOON_1F_ENTRY,
    )
    _emit(progress, emulator, "mt_moon_entered", "Entered Mt. Moon", 7)

    mt_moon_ledger = _MtMoonTraversalLedger()
    (
        mt_moon_zubat_search_flees,
        mt_moon_zubat_search_attempts,
        mt_moon_zubat_movement_retries,
    ) = _capture_mt_moon_zubat(
        chapter_executor,
        reader,
        emulator,
        timing,
        mt_moon_ledger,
    )
    _move_mt_moon_with_seed_waits(
        chapter_executor,
        reader,
        MT_MOON_1F_DIRECTIONS[4:43],
        MT_MOON_1F_PRE_TM_SEED_WAITS,
        "Mt. Moon 1F route before recovery Potion",
        expected_map_id=MapId.MT_MOON_1F,
        ledger=mt_moon_ledger,
    )
    _collect_mt_moon_recovery_potion(
        chapter_executor,
        reader,
        emulator,
        timing,
        mt_moon_ledger,
    )
    _move_mt_moon(
        chapter_executor,
        reader,
        MT_MOON_1F_DIRECTIONS[43:72],
        "Mt. Moon 1F route from recovery Potion to TM01",
        expected_map_id=MapId.MT_MOON_1F,
        ledger=mt_moon_ledger,
    )
    _collect_mt_moon_tm01(
        chapter_executor,
        reader,
        emulator,
        timing,
        mt_moon_ledger,
    )
    _teach_mt_moon_mega_punch(
        chapter_executor,
        reader,
        emulator,
        timing,
    )
    _move_mt_moon_with_seed_waits(
        chapter_executor,
        reader,
        MT_MOON_1F_DIRECTIONS[72:],
        MT_MOON_1F_POST_TM_SEED_WAITS,
        "Mt. Moon 1F route after TM01",
        expected_map_id=MapId.MT_MOON_1F,
        ledger=mt_moon_ledger,
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    mt_moon_b1f_reached, _ = _observe_boundary(
        reader,
        tracker,
        CeruleanBoundary.MT_MOON_B1F_DESCENT,
    )
    _emit(
        progress,
        emulator,
        "mt_moon_b1f",
        "Reached the connected Mt. Moon B1F route",
        8,
    )

    _move_mt_moon_with_seed_waits(
        chapter_executor,
        reader,
        MT_MOON_B1F_DIRECTIONS,
        MT_MOON_B1F_SEED_WAITS,
        "Mt. Moon B1F legal route",
        expected_map_id=MapId.MT_MOON_B1F,
        ledger=mt_moon_ledger,
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    mt_moon_b2f_reached, _ = _observe_boundary(
        reader,
        tracker,
        CeruleanBoundary.MT_MOON_B2F_ENTRY,
    )
    _emit(
        progress,
        emulator,
        "mt_moon_b2f",
        "Reached the fossil-side Mt. Moon B2F route",
        9,
    )

    _move_mt_moon_with_seed_waits(
        chapter_executor,
        reader,
        MT_MOON_B2F_TO_ROCKET_DIRECTIONS,
        MT_MOON_B2F_SEED_WAITS,
        "Mt. Moon Rocket approach",
        expected_map_id=MapId.MT_MOON_B2F,
        ledger=mt_moon_ledger,
    )
    _move(
        chapter_executor,
        reader,
        ROCKET_TRIGGER_DIRECTIONS,
        "Mt. Moon Rocket sight trigger",
        allow_trainer_trigger=True,
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    rocket_battle = _enter_trainer_battle(
        chapter_executor,
        reader,
        timing,
        MapId.MT_MOON_B2F,
        "Mt. Moon required Rocket",
    )
    rocket_battle_evidence = reader.read_cerulean_chapter_state(rocket_battle)
    _observe_semantic(
        tracker,
        rocket_battle_evidence,
        CeruleanPhase.REQUIRED_ROCKET_BATTLE,
        "Mt. Moon required Rocket",
    )
    _emit(
        progress,
        emulator,
        "required_rocket",
        "Verified the unavoidable Team Rocket battle",
        10,
    )
    _select_battle_move(
        chapter_executor,
        reader,
        timing,
        slot=3,
        label="Mt. Moon required Rocket",
    )
    rocket_defeated = _finish_battle(
        chapter_executor,
        reader,
        timing,
        MapId.MT_MOON_B2F,
        "Mt. Moon required Rocket",
    )
    rocket_victory_evidence = reader.read_cerulean_chapter_state(rocket_defeated)
    if (
        not rocket_victory_evidence.beat_required_rocket
        or rocket_defeated.party_species_ids
        != (WARTORTLE_SPECIES_ID, ZUBAT_SPECIES_ID)
        or rocket_defeated.first_party_level != 16
    ):
        raise CeruleanChapterError(
            "The required Rocket victory or Squirtle evolution did not persist."
        )
    for _ in range(timing.rocket_cleanup_pulses):
        chapter_executor.execute(MacroAction(MacroActionKind.CANCEL))
        _wait(chapter_executor, timing.dialogue_wait_frames)

    _move_mt_moon(
        chapter_executor,
        reader,
        ROCKET_TO_SUPER_NERD_DIRECTIONS[:-1],
        "Super Nerd approach",
        expected_map_id=MapId.MT_MOON_B2F,
        ledger=mt_moon_ledger,
    )
    _move(
        chapter_executor,
        reader,
        ROCKET_TO_SUPER_NERD_DIRECTIONS[-1:],
        "Super Nerd sight trigger",
        allow_trainer_trigger=True,
    )
    super_nerd_battle = _enter_trainer_battle(
        chapter_executor,
        reader,
        timing,
        MapId.MT_MOON_B2F,
        "Mt. Moon Super Nerd",
    )
    super_nerd_battle_evidence = reader.read_cerulean_chapter_state(super_nerd_battle)
    _observe_semantic(
        tracker,
        super_nerd_battle_evidence,
        CeruleanPhase.SUPER_NERD_BATTLE,
        "Mt. Moon Super Nerd",
    )
    _emit(
        progress,
        emulator,
        "super_nerd",
        "Verified the fossil-guarding Super Nerd battle",
        11,
    )
    _wait(chapter_executor, timing.super_nerd_preselect_wait_frames)
    _select_battle_move(
        chapter_executor,
        reader,
        timing,
        slot=4,
        label="Mt. Moon Super Nerd",
    )
    super_nerd_defeated = _finish_battle(
        chapter_executor,
        reader,
        timing,
        MapId.MT_MOON_B2F,
        "Mt. Moon Super Nerd",
        emulator=emulator,
        recovery_hp_threshold=MT_MOON_SUPER_NERD_RECOVERY_HP,
        recovery_potion_floor=ROUTE_3_PROTECTED_POTION_FLOOR,
    )
    super_nerd_victory_evidence = reader.read_cerulean_chapter_state(super_nerd_defeated)
    if not super_nerd_victory_evidence.beat_super_nerd:
        raise CeruleanChapterError("The Super Nerd event did not persist.")

    _move_mt_moon(
        chapter_executor,
        reader,
        SUPER_NERD_TO_HELIX_DIRECTIONS,
        "Helix Fossil approach",
        expected_map_id=MapId.MT_MOON_B2F,
        ledger=mt_moon_ledger,
    )
    chapter_executor.execute(MacroAction(MacroActionKind.INTERACT))
    fossil_obtained, fossil_evidence = _obtain_helix_fossil(
        chapter_executor,
        reader,
        tracker,
        timing,
    )
    _emit(
        progress,
        emulator,
        "helix_fossil",
        "Obtained the Helix Fossil",
        12,
    )

    _wait(chapter_executor, MT_MOON_B2F_EXIT_SEED_WAIT)
    _move_mt_moon(
        chapter_executor,
        reader,
        MT_MOON_B2F_EXIT_DIRECTIONS,
        "Mt. Moon B2F exit route",
        expected_map_id=MapId.MT_MOON_B2F,
        ledger=mt_moon_ledger,
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    mt_moon_b1f_ascent, _ = _observe_boundary(
        reader,
        tracker,
        CeruleanBoundary.MT_MOON_B1F_ASCENT,
    )
    _emit(
        progress,
        emulator,
        "mt_moon_b1f_ascent",
        "Reached the legal Mt. Moon exit ladder",
        13,
    )
    _wait(chapter_executor, MT_MOON_B1F_EXIT_SEED_WAIT)
    _move_mt_moon(
        chapter_executor,
        reader,
        MT_MOON_B1F_EXIT_DIRECTIONS,
        "Mt. Moon final exit",
        expected_map_id=MapId.MT_MOON_B1F,
        ledger=mt_moon_ledger,
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    mt_moon_exited, _ = _observe_boundary(
        reader,
        tracker,
        CeruleanBoundary.ROUTE_4_MT_MOON_EXIT,
    )
    _emit(
        progress,
        emulator,
        "mt_moon_exited",
        "Exited Mt. Moon onto Route 4",
        14,
    )

    _move(
        chapter_executor,
        reader,
        ROUTE_4_FIRST_LEDGE_APPROACH_DIRECTIONS,
        "Route 4 first ledge approach",
    )
    _move(
        chapter_executor,
        reader,
        ROUTE_4_FIRST_LEDGE_DIRECTIONS,
        "Route 4 first ledge",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _move(
        chapter_executor,
        reader,
        ROUTE_4_MIDDLE_DIRECTIONS,
        "Route 4 middle route",
    )
    _move(
        chapter_executor,
        reader,
        ROUTE_4_SECOND_LEDGE_DIRECTIONS,
        "Route 4 second ledge",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _move(
        chapter_executor,
        reader,
        ROUTE_4_FINAL_APPROACH_DIRECTIONS,
        "Cerulean approach",
    )
    _move(
        chapter_executor,
        reader,
        ROUTE_4_TO_CERULEAN_DIRECTIONS,
        "Cerulean transition",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    cerulean_reached, cerulean_evidence = _observe_boundary(
        reader,
        tracker,
        CeruleanBoundary.CERULEAN_WEST_ENTRY,
    )
    _wait(chapter_executor, timing.final_stability_wait_frames)
    stable_cerulean = reader.read()
    stable_cerulean_evidence = reader.read_cerulean_chapter_state(stable_cerulean)
    if not stable_cerulean_evidence.cerulean_snapshot:
        raise CeruleanChapterError("Cerulean arrival did not remain semantically stable.")
    cerulean_reached = stable_cerulean
    cerulean_evidence = stable_cerulean_evidence
    _emit(progress, emulator, "cerulean_reached", "Reached Cerulean City", 15)

    report = CeruleanChapterReport(
        starting_brock_evidence=starting_brock_evidence,
        route_3_reached=route_3_reached,
        route_3_battles=tuple(route_3_battles),
        route_3_victories=tuple(route_3_victories),
        route_4_reached=route_4_reached,
        mt_moon_entered=mt_moon_entered,
        mt_moon_b1f_reached=mt_moon_b1f_reached,
        mt_moon_b2f_reached=mt_moon_b2f_reached,
        rocket_battle=rocket_battle,
        rocket_defeated=rocket_defeated,
        super_nerd_battle=super_nerd_battle,
        super_nerd_defeated=super_nerd_defeated,
        fossil_obtained=fossil_obtained,
        mt_moon_b1f_ascent=mt_moon_b1f_ascent,
        mt_moon_exited=mt_moon_exited,
        cerulean_reached=cerulean_reached,
        route_3_battle_evidence=tuple(route_3_battle_evidence),
        route_3_victory_evidence=tuple(route_3_victory_evidence),
        route_3_wild_flees=route_3_wild_flees,
        route_3_movement_retries=route_3_movement_retries,
        mt_moon_zubat_search_flees=mt_moon_zubat_search_flees,
        mt_moon_zubat_search_attempts=mt_moon_zubat_search_attempts,
        mt_moon_zubat_movement_retries=mt_moon_zubat_movement_retries,
        mt_moon_wild_flees=tuple(mt_moon_ledger.flees),
        mt_moon_movement_retries=mt_moon_ledger.movement_retries,
        rocket_battle_evidence=rocket_battle_evidence,
        rocket_victory_evidence=rocket_victory_evidence,
        super_nerd_battle_evidence=super_nerd_battle_evidence,
        super_nerd_victory_evidence=super_nerd_victory_evidence,
        fossil_evidence=fossil_evidence,
        cerulean_evidence=cerulean_evidence,
        reached_boundaries=tracker.reached_boundaries,
        observed_route_3_trainers=tracker.observed_route_3_trainers,
        saw_required_rocket_battle=tracker.saw_required_rocket_battle,
        saw_super_nerd_battle=tracker.saw_super_nerd_battle,
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=chapter_executor.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise CeruleanChapterError(
            "The Brock-to-Cerulean chapter failed its public evidence contract."
        )
    return report


def _move(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    label: str,
    *,
    allow_trainer_trigger: bool = False,
) -> RawGameState:
    state = reader.read()
    direction_list = tuple(directions)
    for step, direction in enumerate(direction_list, start=1):
        if state.battle_state:
            raise CeruleanChapterError(f"Unexpected battle interrupted {label} before step {step}.")
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        state = reader.read()
        is_allowed_final_trigger = (
            allow_trainer_trigger and step == len(direction_list) and state.battle_state == 2
        )
        if state.battle_state and not is_allowed_final_trigger:
            raise CeruleanChapterError(f"Unexpected battle interrupted {label} at step {step}.")
        if state.first_party_hp == 0:
            raise CeruleanChapterError(
                f"Squirtle's lineage fainted during {label}: "
                f"map={state.map_id!r}, coordinate={(state.player_x, state.player_y)!r}, "
                f"status={state.first_party_status!r}."
            )
    return state


def _move_with_seed_waits(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    directions: tuple[str, ...],
    waits: tuple[tuple[int, int], ...],
    label: str,
) -> RawGameState:
    wait_by_step: Mapping[int, int] = dict(waits)
    if len(wait_by_step) != len(waits) or any(
        step < 1 or step > len(directions) for step in wait_by_step
    ):
        raise CeruleanChapterError(f"{label} has an invalid deterministic wait schedule.")
    state = reader.read()
    for step, direction in enumerate(directions, start=1):
        if step in wait_by_step:
            _wait(executor, wait_by_step[step])
        state = _move(executor, reader, (direction,), f"{label} step {step}")
    return state


def _move_mt_moon(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    label: str,
    *,
    expected_map_id: MapId,
    ledger: _MtMoonTraversalLedger,
) -> RawGameState:
    """Move through one cave segment while extending the chapter-wide ledger."""

    if ledger.remaining_flees < 0:
        raise CeruleanChapterError("Mt. Moon traversal exceeded its cumulative flee budget.")
    state, flees, retries = move_with_wild_flees(
        executor,
        reader,
        directions,
        label,
        expected_map_id=expected_map_id,
        route_name="Mt. Moon",
        maximum_flees=ledger.remaining_flees,
        stabilization_frames=ROUTE_3_WILD_STABILIZATION_FRAMES,
        maximum_step_attempts=ROUTE_3_MAX_STEP_ATTEMPTS,
        step_retry_wait_frames=ROUTE_3_STEP_RETRY_WAIT_FRAMES,
        error_type=CeruleanChapterError,
    )
    ledger.flees.extend(flees)
    ledger.movement_retries += retries
    return state


def _move_mt_moon_with_seed_waits(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    directions: tuple[str, ...],
    waits: tuple[tuple[int, int], ...],
    label: str,
    *,
    expected_map_id: MapId,
    ledger: _MtMoonTraversalLedger,
) -> RawGameState:
    """Retain the historical waits without losing closed-loop cave receipts."""

    wait_by_step: Mapping[int, int] = dict(waits)
    if len(wait_by_step) != len(waits) or any(
        step < 1 or step > len(directions) for step in wait_by_step
    ):
        raise CeruleanChapterError(f"{label} has an invalid deterministic wait schedule.")
    state = reader.read()
    for step, direction in enumerate(directions, start=1):
        if step in wait_by_step:
            _wait(executor, wait_by_step[step])
        state = _move_mt_moon(
            executor,
            reader,
            (direction,),
            f"{label} step {step}",
            expected_map_id=expected_map_id,
            ledger=ledger,
        )
    return state


def _capture_mt_moon_zubat(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CeruleanTiming,
    ledger: _MtMoonTraversalLedger,
) -> tuple[tuple[Route1WildFleeEvidence, ...], int, int]:
    """Catch the pinned level-seven Zubat with the sole Poké Ball."""

    _wait(executor, MT_MOON_ZUBAT_SEED_WAIT)
    _move_mt_moon(
        executor,
        reader,
        MT_MOON_1F_DIRECTIONS[:3],
        "Mt. Moon Zubat approach",
        expected_map_id=MapId.MT_MOON_1F,
        ledger=ledger,
    )
    encounter, search_flees, movement_retries, search_attempts = _seek_mt_moon_zubat(
        executor,
        reader,
    )
    if len(search_flees) > ledger.remaining_flees:
        raise CeruleanChapterError("Mt. Moon Zubat search exhausted the cave-wide flee budget.")
    ledger.flees.extend(search_flees)
    ledger.movement_retries += movement_retries
    if (
        encounter.map_id != MapId.MT_MOON_1F
        or encounter.battle_state != 1
        or encounter.enemy_species_id != ZUBAT_SPECIES_ID
        or encounter.enemy_level != 7
        or encounter.enemy_hp is None
        or encounter.enemy_hp != encounter.enemy_max_hp
        or not 20 <= encounter.enemy_hp <= 30
        or encounter.party_species_ids != (SQUIRTLE_SPECIES_ID,)
        or _bag_quantity(emulator, ItemId.POKE_BALL) != 1
    ):
        raise CeruleanChapterError(
            "Mt. Moon capture missed the qualified Zubat encounter: "
            f"map={encounter.map_id!r}, battle={encounter.battle_state!r}, "
            f"species={encounter.enemy_species_id!r}, level={encounter.enemy_level!r}, "
            f"hp={(encounter.enemy_hp, encounter.enemy_max_hp)!r}, "
            f"party={encounter.party_species_ids!r}, "
            f"balls={_bag_quantity(emulator, ItemId.POKE_BALL)}."
        )

    _wait(executor, MT_MOON_ZUBAT_PRE_THROW_WAIT)
    _select_battle_move(
        executor,
        reader,
        timing,
        slot=3,
        label="Mt. Moon Zubat Bubble weakening",
        expected_battle_state=1,
    )
    weakened = reader.read()
    if (
        weakened.map_id != MapId.MT_MOON_1F
        or weakened.battle_state != 1
        or weakened.enemy_species_id != ZUBAT_SPECIES_ID
        or weakened.enemy_level != 7
        or weakened.enemy_hp is None
        or not 0 < weakened.enemy_hp < encounter.enemy_hp
        or weakened.party_species_ids != (SQUIRTLE_SPECIES_ID,)
        or _bag_quantity(emulator, ItemId.POKE_BALL) != 1
    ):
        raise CeruleanChapterError("Mt. Moon Zubat weakening failed its living target gate.")
    _navigate_wild_main_command(executor, reader, timing, target=1)
    _pulse(executor, MacroActionKind.CONFIRM, frames=120)
    for _ in range(20):
        items = _bag_item_ids(emulator)
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        target = items.index(ItemId.POKE_BALL) if ItemId.POKE_BALL in items else -1
        if absolute == target >= 0:
            break
        if target < 0:
            raise CeruleanChapterError("Mt. Moon capture lost its sole Poké Ball.")
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if absolute < target else "up",
            120,
        )
    else:
        raise CeruleanChapterError("Mt. Moon capture could not select the Poké Ball.")

    _pulse(executor, MacroActionKind.CONFIRM, frames=360)
    for _ in range(9):
        _pulse(executor, MacroActionKind.CANCEL, frames=180)
    settled = reader.read()
    captured_hp = _read_u16(emulator, RamAddress.PARTY_MON_2_HP)
    captured_max_hp = _read_u16(emulator, RamAddress.PARTY_MON_2_MAX_HP)
    if (
        settled.map_id != MapId.MT_MOON_1F
        or (settled.player_x, settled.player_y) not in {(14, 31), (14, 32)}
        or settled.battle_state != 0
        or settled.party_species_ids
        != (SQUIRTLE_SPECIES_ID, ZUBAT_SPECIES_ID)
        or emulator.read_u8(RamAddress.PARTY_MON_2_LEVEL) != 7
        or not _is_persistent_weakened_capture_hp(
            captured_hp,
            captured_max_hp,
            weakened.enemy_hp,
        )
        or _bag_quantity(emulator, ItemId.POKE_BALL) != 0
        or not reader.read_input_readiness().ready
    ):
        raise CeruleanChapterError("Mt. Moon Zubat capture failed its persistent gate.")
    if (settled.player_x, settled.player_y) == (14, 32):
        _, return_flees, return_retries = move_with_wild_flees(
            executor,
            reader,
            ("up",),
            "Mt. Moon Zubat route rejoin",
            expected_map_id=MapId.MT_MOON_1F,
            route_name="Mt. Moon",
            maximum_flees=min(
                MT_MOON_ZUBAT_SEARCH_MAX_FLEES - len(search_flees),
                ledger.remaining_flees,
            ),
            stabilization_frames=ROUTE_3_WILD_STABILIZATION_FRAMES,
            maximum_step_attempts=ROUTE_3_MAX_STEP_ATTEMPTS,
            step_retry_wait_frames=ROUTE_3_STEP_RETRY_WAIT_FRAMES,
            error_type=CeruleanChapterError,
        )
        search_flees += return_flees
        movement_retries += return_retries
        ledger.flees.extend(return_flees)
        ledger.movement_retries += return_retries
    _expect_position(reader.read(), MapId.MT_MOON_1F, 14, 31, "Mt. Moon Zubat route rejoin")
    return search_flees, search_attempts, movement_retries


def _seek_mt_moon_zubat(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
) -> tuple[
    RawGameState,
    tuple[Route1WildFleeEvidence, ...],
    int,
    int,
]:
    """Search one reversible grass edge for the exact level-seven Zubat lesson."""

    origin = reader.read()
    if (
        origin.map_id != MapId.MT_MOON_1F
        or (origin.player_x, origin.player_y) != (14, 32)
        or origin.battle_state != 0
    ):
        raise CeruleanChapterError("Mt. Moon Zubat search lacks its exact origin.")
    flees: tuple[Route1WildFleeEvidence, ...] = ()
    movement_retries = 0
    for search_attempt in range(1, MT_MOON_ZUBAT_SEARCH_CYCLES + 1):
        before = reader.read()
        if (
            before.map_id != MapId.MT_MOON_1F
            or (before.player_x, before.player_y) != (14, 32)
            or before.battle_state != 0
        ):
            raise CeruleanChapterError("Mt. Moon Zubat search lost its reversible origin.")
        executor.execute(MacroAction(MacroActionKind.MOVE, "up"))
        _wait(executor, 1)
        observed = reader.read()
        consumed = (observed.player_x, observed.player_y) == (14, 31)
        if observed.battle_state:
            if observed.battle_state != 1 or observed.map_id != MapId.MT_MOON_1F:
                raise CeruleanChapterError("Mt. Moon Zubat search met a non-wild battle.")
            if observed.enemy_species_id == ZUBAT_SPECIES_ID and observed.enemy_level == 7:
                return observed, flees, movement_retries, search_attempt
            if len(flees) >= MT_MOON_ZUBAT_SEARCH_MAX_FLEES:
                raise CeruleanChapterError("Mt. Moon Zubat search exhausted its flee budget.")
            flees += (
                flee_wild(
                    executor,
                    reader,
                    observed,
                    expected_map_id=MapId.MT_MOON_1F,
                    route_name="Mt. Moon",
                    stabilization_frames=ROUTE_3_WILD_STABILIZATION_FRAMES,
                    error_type=CeruleanChapterError,
                ),
            )
        elif not consumed:
            if (observed.player_x, observed.player_y) != (14, 32):
                raise CeruleanChapterError("Mt. Moon Zubat search drifted off its grass edge.")
            movement_retries += 1
            _wait(executor, ROUTE_3_STEP_RETRY_WAIT_FRAMES)
            continue

        if consumed:
            _, return_flees, return_retries = move_with_wild_flees(
                executor,
                reader,
                ("down",),
                "Mt. Moon Zubat search-origin return",
                expected_map_id=MapId.MT_MOON_1F,
                route_name="Mt. Moon",
                maximum_flees=MT_MOON_ZUBAT_SEARCH_MAX_FLEES - len(flees),
                stabilization_frames=ROUTE_3_WILD_STABILIZATION_FRAMES,
                maximum_step_attempts=ROUTE_3_MAX_STEP_ATTEMPTS,
                step_retry_wait_frames=ROUTE_3_STEP_RETRY_WAIT_FRAMES,
                error_type=CeruleanChapterError,
            )
            flees += return_flees
            movement_retries += return_retries
    raise CeruleanChapterError("Mt. Moon Zubat search exhausted its bounded semantic search.")


def _collect_mt_moon_tm01(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CeruleanTiming,
    ledger: _MtMoonTraversalLedger,
) -> None:
    """Collect TM01 from its legal side room and return to the exact route tile."""

    _expect_position(reader.read(), MapId.MT_MOON_1F, 16, 11, "TM01 detour origin")
    before_toggle = _toggleable_object_flag(emulator, 0x70)
    if before_toggle or _bag_quantity(emulator, ItemId.TM01_MEGA_PUNCH) != 0:
        raise CeruleanChapterError("TM01 detour has an invalid starting gate.")

    _wait(executor, 1)
    _move_mt_moon(
        executor,
        reader,
        ("right",),
        "TM01 B1F warp",
        expected_map_id=MapId.MT_MOON_1F,
        ledger=ledger,
    )
    _wait(executor, timing.transition_wait_frames)
    _expect_position(reader.read(), MapId.MT_MOON_B1F, 25, 9, "TM01 B1F landing")
    _move_mt_moon(
        executor,
        reader,
        _directions("DDL"),
        "TM01 B1F approach",
        expected_map_id=MapId.MT_MOON_B1F,
        ledger=ledger,
    )
    _wait(executor, 1)
    _move_mt_moon(
        executor,
        reader,
        _directions("L" * 7),
        "TM01 B2F warp",
        expected_map_id=MapId.MT_MOON_B1F,
        ledger=ledger,
    )
    _wait(executor, timing.transition_wait_frames)
    _expect_position(reader.read(), MapId.MT_MOON_B2F, 25, 9, "TM01 B2F landing")
    _move_mt_moon(
        executor,
        reader,
        _directions("U" + "R" * 3 + "U" * 3),
        "TM01 pickup approach",
        expected_map_id=MapId.MT_MOON_B2F,
        ledger=ledger,
    )
    _expect_position(reader.read(), MapId.MT_MOON_B2F, 28, 5, "TM01 pickup stance")
    _move(executor, reader, ("right",), "TM01 pickup facing")
    chapter_faced = reader.read()
    if (chapter_faced.player_x, chapter_faced.player_y) != (28, 5):
        raise CeruleanChapterError("TM01 pickup facing did not collide with the item.")
    executor.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(executor, 240)
    for _ in range(12):
        if reader.read_input_readiness().ready:
            break
        _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    else:
        raise CeruleanChapterError("TM01 pickup did not restore input readiness.")
    if (
        _bag_quantity(emulator, ItemId.TM01_MEGA_PUNCH) != 1
        or not _toggleable_object_flag(emulator, 0x70)
    ):
        raise CeruleanChapterError("TM01 pickup failed its item-and-toggle gate.")
    _move_mt_moon(
        executor,
        reader,
        ("right",),
        "TM01 removed-object proof",
        expected_map_id=MapId.MT_MOON_B2F,
        ledger=ledger,
    )
    _expect_position(reader.read(), MapId.MT_MOON_B2F, 29, 5, "TM01 former object tile")
    _move_mt_moon(
        executor,
        reader,
        ("left",),
        "TM01 pickup realignment",
        expected_map_id=MapId.MT_MOON_B2F,
        ledger=ledger,
    )

    _move_mt_moon(
        executor,
        reader,
        _directions("D" * 3 + "L" * 3 + "D"),
        "TM01 B1F return",
        expected_map_id=MapId.MT_MOON_B2F,
        ledger=ledger,
    )
    _wait(executor, timing.transition_wait_frames)
    _expect_position(reader.read(), MapId.MT_MOON_B1F, 17, 11, "TM01 B1F return")
    _move_mt_moon(
        executor,
        reader,
        _directions("R" * 8 + "U" * 2),
        "TM01 1F return",
        expected_map_id=MapId.MT_MOON_B1F,
        ledger=ledger,
    )
    _wait(executor, timing.transition_wait_frames)
    _expect_position(reader.read(), MapId.MT_MOON_1F, 17, 11, "TM01 1F return")
    _move_mt_moon(
        executor,
        reader,
        ("left",),
        "TM01 route rejoin",
        expected_map_id=MapId.MT_MOON_1F,
        ledger=ledger,
    )
    _expect_position(reader.read(), MapId.MT_MOON_1F, 16, 11, "TM01 route rejoin")


def _collect_mt_moon_recovery_potion(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CeruleanTiming,
    ledger: _MtMoonTraversalLedger,
) -> None:
    """Collect a free cave Potion and return to the exact main-route tile."""

    _expect_position(
        reader.read(),
        MapId.MT_MOON_1F,
        *MT_MOON_POTION_DETOUR_ORIGIN,
        "Mt. Moon recovery Potion detour origin",
    )
    if (
        _toggleable_object_flag(emulator, MT_MOON_POTION_TOGGLE_INDEX)
        or _bag_quantity(emulator, ItemId.POTION) != ROUTE_3_PROTECTED_POTION_FLOOR
    ):
        raise CeruleanChapterError("Mt. Moon recovery Potion has an invalid starting gate.")

    _move_mt_moon(
        executor,
        reader,
        MT_MOON_POTION_APPROACH_DIRECTIONS,
        "Mt. Moon recovery Potion approach",
        expected_map_id=MapId.MT_MOON_1F,
        ledger=ledger,
    )
    _expect_position(
        reader.read(),
        MapId.MT_MOON_1F,
        *MT_MOON_POTION_PICKUP_POSITION,
        "Mt. Moon recovery Potion pickup",
    )
    _pulse(executor, MacroActionKind.MOVE, "left", 60)
    faced = reader.read()
    if (faced.player_x, faced.player_y) != MT_MOON_POTION_PICKUP_POSITION:
        raise CeruleanChapterError("Mt. Moon recovery Potion facing missed the item.")
    executor.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(executor, timing.dialogue_wait_frames)
    for _ in range(12):
        if reader.read_input_readiness().ready:
            break
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)
    else:
        raise CeruleanChapterError("Mt. Moon recovery Potion did not restore field control.")
    if (
        _bag_quantity(emulator, ItemId.POTION) != ROUTE_3_PROTECTED_POTION_FLOOR + 1
        or not _toggleable_object_flag(emulator, MT_MOON_POTION_TOGGLE_INDEX)
    ):
        raise CeruleanChapterError("Mt. Moon recovery Potion failed its item-and-toggle gate.")

    _move_mt_moon(
        executor,
        reader,
        MT_MOON_POTION_RETURN_DIRECTIONS,
        "Mt. Moon recovery Potion return",
        expected_map_id=MapId.MT_MOON_1F,
        ledger=ledger,
    )
    _expect_position(
        reader.read(),
        MapId.MT_MOON_1F,
        *MT_MOON_POTION_DETOUR_ORIGIN,
        "Mt. Moon recovery Potion route rejoin",
    )


def _teach_mt_moon_mega_punch(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CeruleanTiming,
) -> None:
    """Turn the optional TM01 detour into a verified Rocket-battle lesson."""

    before = reader.read()
    if (
        before.map_id != MapId.MT_MOON_1F
        or (before.player_x, before.player_y) != (16, 11)
        or before.battle_state != 0
        or before.party_species_ids != (SQUIRTLE_SPECIES_ID, ZUBAT_SPECIES_ID)
        or before.first_party_moves is None
        or before.first_party_moves[2] != BUBBLE_MOVE_ID
        or _bag_quantity(emulator, ItemId.TM01_MEGA_PUNCH) != 1
        or not reader.read_input_readiness().ready
    ):
        raise CeruleanChapterError("Mt. Moon TM01 teaching has an invalid starting gate.")

    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, timing.dialogue_wait_frames)
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 2:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < 2 else "up",
            timing.move_cursor_wait_frames,
        )
    else:
        raise CeruleanChapterError("Mt. Moon TM01 teaching could not select ITEM.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)

    for _ in range(24):
        items = _bag_item_ids(emulator)
        if ItemId.TM01_MEGA_PUNCH not in items:
            raise CeruleanChapterError("Mt. Moon TM01 teaching lost the collected TM.")
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        target = items.index(ItemId.TM01_MEGA_PUNCH)
        if absolute == target:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if absolute < target else "up",
            timing.move_cursor_wait_frames,
        )
    else:
        raise CeruleanChapterError("Mt. Moon TM01 teaching could not select TM01.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)

    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (0, 1):
            break
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)
    else:
        raise CeruleanChapterError("Mt. Moon TM01 teaching did not reach party selection.")

    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 0:
            break
        _pulse(executor, MacroActionKind.MOVE, "up", timing.move_cursor_wait_frames)
    else:
        raise CeruleanChapterError("Mt. Moon TM01 teaching could not select Squirtle.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)

    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (5, 8):
            break
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)
    else:
        raise CeruleanChapterError("Mt. Moon TM01 teaching did not reach move deletion.")

    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 2:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < 2 else "up",
            timing.move_cursor_wait_frames,
        )
    else:
        raise CeruleanChapterError("Mt. Moon TM01 teaching could not select Bubble slot three.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)

    expected_moves = (
        before.first_party_moves[0],
        before.first_party_moves[1],
        MEGA_PUNCH_MOVE_ID,
        before.first_party_moves[3],
    )
    for _ in range(24):
        learned = reader.read()
        if (
            learned.first_party_moves == expected_moves
            and _bag_quantity(emulator, ItemId.TM01_MEGA_PUNCH) == 0
        ):
            break
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)
    else:
        raise CeruleanChapterError("Mt. Moon TM01 did not replace Bubble and consume the item.")

    for _ in range(2):
        _pulse(executor, MacroActionKind.CANCEL, frames=timing.dialogue_wait_frames)
    for _ in range(12):
        if reader.read_input_readiness().ready:
            return
        _pulse(executor, MacroActionKind.CANCEL, frames=timing.dialogue_wait_frames)
    raise CeruleanChapterError("Mt. Moon TM01 teaching did not restore field control.")


def _navigate_wild_main_command(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CeruleanTiming,
    *,
    target: int,
) -> None:
    for _ in range(32):
        raw = reader.read()
        if raw.battle_state != 1:
            raise CeruleanChapterError("Wild-battle navigation left the active encounter.")
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _pulse(executor, MacroActionKind.CONFIRM, frames=180)
            continue
        if menu.phase is BattleMenuPhase.MOVE:
            _pulse(executor, MacroActionKind.CANCEL, frames=120)
            continue
        current = menu.selected_main_command
        if current == target:
            return
        direction = {
            1: {0: "down", 2: "left", 3: "left"},
        }.get(target, {}).get(current)
        if direction is None:
            raise CeruleanChapterError("Wild battle exposed an invalid main-menu cursor.")
        _pulse(executor, MacroActionKind.MOVE, direction, timing.move_cursor_wait_frames)
    raise CeruleanChapterError("Wild battle menu navigation exceeded its bound.")


def _bag_item_ids(emulator: EmulatorState) -> tuple[int, ...]:
    count = emulator.read_u8(RamAddress.NUM_BAG_ITEMS)
    if not 0 <= count <= 20:
        raise CeruleanChapterError("Bag item count is outside the supported bound.")
    return tuple(
        emulator.read_u8(int(RamAddress.BAG_ITEMS) + index * 2)
        for index in range(count)
    )


def _read_u16(emulator: EmulatorState, address: RamAddress) -> int:
    return (
        emulator.read_u8(int(address)) * 0x100
        + emulator.read_u8(int(address) + 1)
    )


def _is_persistent_weakened_capture_hp(
    captured_hp: int,
    captured_max_hp: int,
    weakened_enemy_hp: int,
) -> bool:
    return (
        0 < captured_hp < captured_max_hp
        and abs(captured_hp - weakened_enemy_hp) <= 1
    )


def _toggleable_object_flag(emulator: EmulatorState, index: int) -> bool:
    if not 0 <= index < 0x100:
        raise CeruleanChapterError("Toggleable object index is outside one byte.")
    address = int(RamAddress.TOGGLEABLE_OBJECT_FLAGS) + index // 8
    return bool(emulator.read_u8(address) & (1 << (index % 8)))


def _heal(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CeruleanTiming,
    center_map: MapId,
    label: str,
    *,
    emulator: EmulatorState | None = None,
    withdraw_pc_potion: bool = False,
) -> RawGameState:
    _expect_position(reader.read(), center_map, 3, 7, label)
    _move(executor, reader, CENTER_HEAL_APPROACH_DIRECTIONS, f"{label} nurse")
    for _ in range(timing.heal_dialogue_pulses):
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    healed = reader.read()
    pp = tuple(value & 0x3F for value in (healed.first_party_pp or ()))
    learned_pp = tuple(
        value
        for move, value in zip(
            healed.first_party_moves or (),
            pp,
            strict=False,
        )
        if move
    )
    if (
        healed.map_id != center_map
        or healed.battle_state != 0
        or healed.first_party_hp is None
        or healed.first_party_hp != healed.first_party_max_hp
        or healed.first_party_status != 0
        or not learned_pp
        or not all(value > 0 for value in learned_pp)
    ):
        raise CeruleanChapterError(f"{label} failed its persistent healing gate.")
    if withdraw_pc_potion:
        if emulator is None or center_map is not MapId.PEWTER_POKECENTER:
            raise CeruleanChapterError("Early PC Potion withdrawal requires Pewter evidence.")
        _withdraw_pewter_pc_potion(executor, reader, emulator, timing)
    _move(executor, reader, CENTER_EXIT_DIRECTIONS, f"{label} exit")
    _wait(executor, timing.transition_wait_frames)
    return reader.read()


def _withdraw_pewter_pc_potion(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CeruleanTiming,
) -> None:
    """Withdraw the guaranteed new-game Potion before the Route 3 poison lesson."""

    before = reader.read()
    before_count = emulator.read_u8(RamAddress.NUM_BAG_ITEMS)
    before_quantity = _bag_quantity(emulator, ItemId.POTION)
    if (
        before.map_id != MapId.PEWTER_POKECENTER
        or (before.player_x, before.player_y) != (3, 3)
        or before.battle_state != 0
        or not reader.read_input_readiness().ready
        or not 0 <= before_count < 20
        or before_quantity
        not in {
            PEWTER_POTION_PURCHASE_QUANTITY,
            PEWTER_LOSS_POTION_PURCHASE_QUANTITY,
        }
    ):
        raise CeruleanChapterError("Pewter PC Potion withdrawal has an invalid starting gate.")

    _approach_center_pc(executor, reader, emulator, timing, MapId.PEWTER_POKECENTER)
    _pulse(executor, MacroActionKind.INTERACT, frames=timing.dialogue_wait_frames)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)
    for _ in range(4):
        if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) == 1:
            break
        _pulse(executor, MacroActionKind.MOVE, "down", timing.dialogue_wait_frames)
    else:
        raise CeruleanChapterError("Pewter PC could not select RED's PC.")
    for _ in range(3):
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 0:
        raise CeruleanChapterError("Pewter PC did not expose WITHDRAW ITEM.")
    for _ in range(3):
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)
    if (
        _bag_quantity(emulator, ItemId.POTION) != before_quantity + 1
        or emulator.read_u8(RamAddress.NUM_BAG_ITEMS) != before_count
    ):
        raise CeruleanChapterError("Pewter PC did not withdraw exactly one Potion.")
    for _ in range(4):
        _pulse(executor, MacroActionKind.CANCEL, frames=timing.dialogue_wait_frames)
    _return_from_center_pc(executor, reader, timing, MapId.PEWTER_POKECENTER)


def _approach_center_pc(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CeruleanTiming,
    center_map: MapId,
) -> None:
    _move(executor, reader, CENTER_HEAL_TO_PC_DIRECTIONS, "Pewter PC approach")
    target = (13, 4)
    for attempt in range(24):
        state = reader.read()
        position = (state.player_x, state.player_y)
        if position == target:
            break
        if state.map_id != center_map or state.battle_state != 0:
            raise CeruleanChapterError("Pewter PC approach left its safe Center map.")
        if state.player_x is None or state.player_y is None:
            raise CeruleanChapterError("Pewter PC approach lacks coordinates.")
        if state.player_y < target[1]:
            direction = "down"
        elif state.player_y > target[1]:
            direction = "up"
        elif state.player_x < target[0]:
            direction = "right"
        else:
            direction = "left"
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        moved = reader.read()
        if (moved.player_x, moved.player_y) == position:
            _wait(executor, max(1, timing.dialogue_wait_frames // 4) * (attempt + 1))
    else:
        raise CeruleanChapterError("Pewter PC approach exhausted its movement bound.")
    _pulse(executor, MacroActionKind.MOVE, "up", timing.dialogue_wait_frames)
    faced = reader.read()
    if (
        (faced.player_x, faced.player_y) != target
        or emulator.read_u8(RamAddress.PLAYER_FACING_DIRECTION) != 0x04
    ):
        raise CeruleanChapterError("Pewter PC approach missed its interaction gate.")


def _return_from_center_pc(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CeruleanTiming,
    center_map: MapId,
) -> None:
    _move(executor, reader, CENTER_PC_TO_HEAL_DIRECTIONS, "Pewter PC return")
    target = (3, 3)
    for attempt in range(24):
        state = reader.read()
        position = (state.player_x, state.player_y)
        if position == target:
            return
        if state.map_id != center_map or state.battle_state != 0:
            raise CeruleanChapterError("Pewter PC return left its safe Center map.")
        if state.player_x is None or state.player_y is None:
            raise CeruleanChapterError("Pewter PC return lacks coordinates.")
        if state.player_y < target[1]:
            direction = "down"
        elif state.player_y > target[1]:
            direction = "up"
        elif state.player_x < target[0]:
            direction = "right"
        else:
            direction = "left"
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        moved = reader.read()
        if (moved.player_x, moved.player_y) == position:
            _wait(executor, max(1, timing.dialogue_wait_frames // 4) * (attempt + 1))
    raise CeruleanChapterError("Pewter PC return exhausted its movement bound.")


def _use_route_3_recovery_potion(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CeruleanTiming,
) -> None:
    """Spend only RED's PC Potion to survive the first Route 3 recovery walk."""

    before = reader.read()
    before_quantity = _bag_quantity(emulator, ItemId.POTION)
    expected_quantity = before_quantity - 1
    if (
        before.map_id != MapId.ROUTE_3
        or before.battle_state != 0
        or before.first_party_hp is None
        or before.first_party_max_hp is None
        or not 0 < before.first_party_hp < before.first_party_max_hp
        or before_quantity
        not in {
            CERULEAN_RIVAL_POTION_RESERVE,
            CERULEAN_RIVAL_POTION_RESERVE + 1,
        }
        or not reader.read_input_readiness().ready
    ):
        raise CeruleanChapterError("Route 3 recovery Potion has an invalid starting gate.")
    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, 180)
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 2:
            break
        _pulse(executor, MacroActionKind.MOVE, "down" if cursor < 2 else "up", 120)
    else:
        raise CeruleanChapterError("Route 3 recovery could not select ITEM.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=180)
    for _ in range(24):
        items = _bag_item_ids(emulator)
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        if ItemId.POTION not in items:
            raise CeruleanChapterError("Route 3 recovery lost its PC Potion.")
        target = items.index(ItemId.POTION)
        if absolute == target:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if absolute < target else "up",
            120,
        )
    else:
        raise CeruleanChapterError("Route 3 recovery could not select its PC Potion.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=180)
    _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    expected_hp = min(before.first_party_max_hp, before.first_party_hp + 20)
    for _ in range(24):
        current = reader.read()
        if (
            current.first_party_hp == expected_hp
            and _bag_quantity(emulator, ItemId.POTION) == expected_quantity
        ):
            break
        _pulse(executor, MacroActionKind.CONFIRM, frames=180)
    else:
        raise CeruleanChapterError("Route 3 recovery Potion missed its exact heal gate.")
    for _ in range(FIELD_ITEM_MENU_CLOSE_PULSES):
        _pulse(executor, MacroActionKind.CANCEL, frames=180)
    for _ in range(6):
        if reader.read_input_readiness().ready:
            break
        _pulse(executor, MacroActionKind.CANCEL, frames=180)
    else:
        raise CeruleanChapterError("Route 3 recovery Potion did not restore field control.")
    final = reader.read()
    if (
        final.map_id != MapId.ROUTE_3
        or final.battle_state != 0
        or final.first_party_hp != expected_hp
        or _bag_quantity(emulator, ItemId.POTION) != expected_quantity
        or not reader.read_input_readiness().ready
    ):
        raise CeruleanChapterError("Route 3 recovery Potion failed its persistent gate.")


def _purchase_early_supplies(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CeruleanTiming,
) -> None:
    """Buy one Ball and the outcome-specific Potion reserve for the northbound route."""

    _expect_position(reader.read(), MapId.PEWTER_MART, 3, 7, "Pewter Mart")
    starting_money = _money(emulator)
    purchase_quantity = (
        PEWTER_LOSS_POTION_PURCHASE_QUANTITY
        if starting_money == PEWTER_SUPPLY_LOSS_STARTING_MONEY
        else PEWTER_POTION_PURCHASE_QUANTITY
    )
    expected_cost = PEWTER_POKE_BALL_PRICE + PEWTER_POTION_PRICE * purchase_quantity
    if (
        starting_money not in PEWTER_SUPPLY_STARTING_MONEY
        or _bag_quantity(emulator, ItemId.POKE_BALL) != 0
        or _bag_quantity(emulator, ItemId.POTION) != 0
    ):
        raise CeruleanChapterError("Pewter supply purchase has an invalid economy gate.")

    _move(executor, reader, PEWTER_MART_CLERK_DIRECTIONS, "Pewter Mart clerk")
    _pulse(executor, MacroActionKind.MOVE, "left", 60)
    faced = reader.read()
    if (
        faced.map_id != MapId.PEWTER_MART
        or (faced.player_x, faced.player_y) != (2, 5)
    ):
        raise CeruleanChapterError("Pewter Mart clerk approach missed its pinned gate.")

    # This exact sequence is the live-qualified product-zero purchase. It
    # returns to the product list with one Poké Ball in the bag.
    for _ in range(4):
        _pulse(executor, MacroActionKind.CONFIRM, frames=180)
    for _ in range(2):
        _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    if _bag_quantity(emulator, ItemId.POKE_BALL) != 1:
        raise CeruleanChapterError("Pewter Mart did not purchase exactly one Poké Ball.")

    for _ in range(4):
        _pulse(executor, MacroActionKind.CANCEL, frames=180)
    if not reader.read_input_readiness().ready:
        raise CeruleanChapterError("Pewter Mart did not close after the Ball purchase.")

    # Reopening the shop resets the product cursor, making the Potion
    # selection independent of the shop's post-purchase cursor behavior.
    _pulse(executor, MacroActionKind.INTERACT, frames=180)
    _pulse(executor, MacroActionKind.CONFIRM, frames=180)
    _pulse(executor, MacroActionKind.MOVE, "down", 180)
    _pulse(executor, MacroActionKind.CONFIRM, frames=180)
    for _ in range(purchase_quantity + 1):
        selected = emulator.read_u8(RamAddress.SHOP_SELECTED_ITEM)
        quantity = emulator.read_u8(RamAddress.SHOP_QUANTITY)
        if selected == ItemId.POTION and quantity == purchase_quantity:
            break
        if selected != ItemId.POTION:
            raise CeruleanChapterError(
                f"Pewter Mart selected {selected:#04x} instead of Potion."
            )
        _pulse(executor, MacroActionKind.MOVE, "up", 120)
    else:
        raise CeruleanChapterError("Pewter Mart Potion quantity selector missed its fixed reserve.")

    for _ in range(8):
        if _bag_quantity(emulator, ItemId.POTION) == purchase_quantity:
            break
        _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    else:
        raise CeruleanChapterError("Pewter Mart did not purchase the fixed Potion reserve.")

    for _ in range(4):
        _pulse(executor, MacroActionKind.CANCEL, frames=180)
    final = reader.read()
    if (
        final.map_id != MapId.PEWTER_MART
        or (final.player_x, final.player_y) != (2, 5)
        or not reader.read_input_readiness().ready
        or _bag_quantity(emulator, ItemId.POKE_BALL) != 1
        or _bag_quantity(emulator, ItemId.POTION)
        != purchase_quantity
        or _money(emulator) != starting_money - expected_cost
    ):
        raise CeruleanChapterError("Pewter Mart supply purchase failed its persistent gate.")


def _leave_pewter_mart(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CeruleanTiming,
) -> None:
    """Exit through the fixed door while tolerating the roaming customer."""

    for attempt in range(12):
        raw = reader.read()
        if raw.map_id != MapId.PEWTER_MART or raw.player_y != 5:
            break
        if raw.player_x == 3:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "right",
            60 * (attempt + 1),
        )
    else:
        raise CeruleanChapterError("Pewter Mart customer blocked the exit column.")
    raw = reader.read()
    if raw.map_id != MapId.PEWTER_MART or (raw.player_x, raw.player_y) != (3, 5):
        raise CeruleanChapterError("Pewter Mart exit column missed its pinned gate.")

    for attempt in range(12):
        raw = reader.read()
        if raw.map_id == MapId.PEWTER_CITY:
            break
        if (
            raw.map_id == MapId.PEWTER_MART
            and (raw.player_x, raw.player_y) == (3, 6)
            and attempt >= 2
        ):
            _pulse(executor, MacroActionKind.MOVE, "right", 60)
        _pulse(executor, MacroActionKind.MOVE, "down", 60)
    else:
        raw = reader.read()
        raise CeruleanChapterError(
            "Pewter Mart door did not return to the city: "
            f"map={raw.map_id!r}, coordinate={(raw.player_x, raw.player_y)!r}."
        )
    _wait(executor, timing.transition_wait_frames)
    _expect_position(reader.read(), MapId.PEWTER_CITY, 23, 18, "Pewter Mart exterior")


def _bag_quantity(emulator: EmulatorState, item: ItemId) -> int:
    count = emulator.read_u8(RamAddress.NUM_BAG_ITEMS)
    if not 0 <= count <= 20:
        raise CeruleanChapterError("Bag item count is outside the supported bound.")
    for index in range(count):
        address = int(RamAddress.BAG_ITEMS) + index * 2
        if emulator.read_u8(address) == item:
            return emulator.read_u8(address + 1)
    return 0


def _money(emulator: EmulatorState) -> int:
    value = 0
    for offset in range(3):
        packed = emulator.read_u8(int(RamAddress.PLAYER_MONEY) + offset)
        high, low = packed >> 4, packed & 0x0F
        if high > 9 or low > 9:
            raise CeruleanChapterError(
                f"Player money contains invalid BCD byte {packed:#04x}."
            )
        value = value * 100 + high * 10 + low
    return value


def _pulse(
    executor: _CountingChapterExecutor,
    kind: MacroActionKind,
    value: str | None = None,
    frames: int = 180,
) -> None:
    executor.execute(MacroAction(kind, value))
    _wait(executor, frames)


def _recover_at_pewter_center(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CeruleanTiming,
    route_prefix: tuple[str, ...],
) -> None:
    _move(
        executor,
        reader,
        _reverse_directions(route_prefix),
        "Route 3 recovery return",
    )
    _move(executor, reader, ("left",), "Route 3 west transition")
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        ROUTE_3_TO_PEWTER_CENTER_DIRECTIONS,
        "Pewter Center recovery route",
    )
    _wait(executor, timing.transition_wait_frames)
    _heal(executor, reader, timing, MapId.PEWTER_POKECENTER, "Pewter Center")
    _move(executor, reader, CENTER_TO_ROUTE_3_DIRECTIONS, "Route 3 recovery entry")
    _wait(executor, timing.transition_wait_frames)
    _expect_position(reader.read(), MapId.ROUTE_3, 0, 10, "Route 3 recovery")
    _move(executor, reader, route_prefix, "Route 3 recovery replay")


def _enter_trainer_battle(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CeruleanTiming,
    expected_map: MapId,
    label: str,
) -> RawGameState:
    for _ in range(timing.max_trainer_intro_pulses):
        raw = reader.read()
        if raw.battle_state == 1:
            raise CeruleanChapterError(f"Unexpected wild battle replaced {label}.")
        if raw.battle_state == 2:
            return raw
        if raw.map_id != expected_map:
            raise CeruleanChapterError(f"{label} left its expected map before battle.")
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    raise CeruleanChapterError(f"{label} failed its bounded trainer-battle gate.")


def _select_battle_move(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CeruleanTiming,
    *,
    slot: int,
    label: str,
    allow_resolved_turn_without_pp: bool = False,
    expected_battle_state: int = 2,
) -> bool:
    if expected_battle_state not in {1, 2}:
        raise CeruleanChapterError(f"{label} has an invalid expected battle state.")
    initial_raw = reader.read()
    initial = _pp_at(initial_raw, slot)
    if initial <= 0:
        raise CeruleanChapterError(f"{label} move slot {slot} had no usable PP.")

    for _ in range(timing.max_main_menu_pulses):
        raw = reader.read()
        if raw.battle_state != expected_battle_state:
            raise CeruleanChapterError(f"{label} left battle before move selection.")
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.MAIN:
            if menu.selected_main_command == 0:
                break
            if menu.selected_main_command in {1, 3}:
                executor.execute(MacroAction(MacroActionKind.MOVE, "up"))
            elif menu.selected_main_command == 2:
                executor.execute(MacroAction(MacroActionKind.MOVE, "left"))
            else:
                raise CeruleanChapterError(f"{label} exposed an invalid main battle-menu command.")
            _wait(executor, timing.move_cursor_wait_frames)
            continue
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    else:
        raise CeruleanChapterError(f"{label} never reached the semantic battle menu.")

    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    _wait(executor, timing.fight_menu_wait_frames)
    for _ in range(timing.max_move_cursor_pulses):
        raw = reader.read()
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is not BattleMenuPhase.MOVE:
            raise CeruleanChapterError(f"{label} left the semantic move menu.")
        if menu.selected_move_slot == slot:
            break
        executor.execute(MacroAction(MacroActionKind.MOVE, "down"))
        _wait(executor, timing.move_cursor_wait_frames)
    else:
        raise CeruleanChapterError(f"{label} never selected move slot {slot}.")

    for attempt in range(timing.max_attack_start_pulses):
        raw = reader.read()
        if _pp_at(raw, slot) < initial:
            return True
        if (
            attempt > 0
            and allow_resolved_turn_without_pp
            and raw.battle_state == expected_battle_state
            and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
            and (
                raw.first_party_hp != initial_raw.first_party_hp
                or raw.enemy_hp != initial_raw.enemy_hp
            )
        ):
            return False
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.selected_move_wait_frames)
        if _pp_at(reader.read(), slot) < initial:
            return True
        if reader.read().battle_state != expected_battle_state:
            raise CeruleanChapterError(f"{label} ended before its persistent PP-decrement gate.")
    raise CeruleanChapterError(f"{label} failed its persistent PP-decrement gate.")


def _finish_battle(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CeruleanTiming,
    expected_map: MapId,
    label: str,
    *,
    emulator: EmulatorState | None = None,
    recovery_hp_threshold: int | None = None,
    recovery_potion_floor: int = 0,
) -> RawGameState:
    if (emulator is None) != (recovery_hp_threshold is None):
        raise CeruleanChapterError(f"{label} has an incomplete recovery policy.")
    saw_battle = False
    stable_reads = 0
    for _ in range(timing.max_battle_pulses):
        before = reader.read()
        if before.map_id != expected_map:
            raise CeruleanChapterError(f"{label} left its expected map.")
        if before.battle_state not in {0, 2}:
            raise CeruleanChapterError(f"{label} changed to an unexpected battle type.")
        saw_battle = saw_battle or before.battle_state == 2
        before_menu = (
            reader.read_battle_menu_state(before)
            if before.battle_state == 2
            else None
        )
        decline_switch = reader.trainer_switch_prompt_visible(before)
        should_recover = (
            emulator is not None
            and recovery_hp_threshold is not None
            and before.battle_state == 2
            and (before.enemy_hp or 0) > 0
            and before_menu is not None
            and before_menu.phase is BattleMenuPhase.MAIN
            and before.first_party_hp is not None
            and 0 < before.first_party_hp <= recovery_hp_threshold
            and _bag_quantity(emulator, ItemId.POTION) > recovery_potion_floor
        )
        if should_recover:
            _use_battle_potion(
                executor,
                reader,
                emulator,
                timing,
                quantity_floor=recovery_potion_floor,
                label=label,
            )
            continue
        executor.execute(
            MacroAction(MacroActionKind.CANCEL if decline_switch else MacroActionKind.CONFIRM)
        )
        _wait(
            executor,
            timing.battle_wait_frames if before.battle_state else timing.dialogue_wait_frames,
        )
        after = reader.read()
        if after.first_party_hp == 0:
            raise CeruleanChapterError(f"Squirtle's lineage fainted during {label}.")
        if after.map_id != expected_map or after.battle_state not in {0, 2}:
            raise CeruleanChapterError(f"{label} left its bounded battle state.")
        saw_battle = saw_battle or after.battle_state == 2
        if saw_battle and after.battle_state == 0 and reader.read_input_readiness().ready:
            stable_reads += 1
            if stable_reads >= 2:
                return after
        else:
            stable_reads = 0
    raise CeruleanChapterError(f"{label} failed its bounded battle-completion gate.")


def _use_battle_potion(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CeruleanTiming,
    *,
    quantity_floor: int,
    label: str,
) -> None:
    """Spend at most one surplus Potion at a verified trainer MAIN boundary."""

    before = reader.read()
    menu = reader.read_battle_menu_state(before)
    before_quantity = _bag_quantity(emulator, ItemId.POTION)
    expected_quantity = before_quantity - 1
    if (
        before.battle_state != 2
        or menu.phase is not BattleMenuPhase.MAIN
        or before.first_party_hp is None
        or before.first_party_max_hp is None
        or not 0 < before.first_party_hp < before.first_party_max_hp
        or before_quantity <= quantity_floor
    ):
        raise CeruleanChapterError(f"{label} Potion has an invalid recovery gate.")

    command = menu.selected_main_command
    directions = {
        0: ("down",),
        1: (),
        2: ("left", "down"),
        3: ("left",),
    }.get(command)
    if directions is None:
        raise CeruleanChapterError(f"{label} exposed an invalid battle command cursor.")
    for direction in directions:
        _pulse(executor, MacroActionKind.MOVE, direction, timing.move_cursor_wait_frames)
    selected = reader.read_battle_menu_state(reader.read())
    if selected.phase is not BattleMenuPhase.MAIN or selected.selected_main_command != 1:
        raise CeruleanChapterError(f"{label} could not select ITEM for recovery.")

    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)
    for _ in range(24):
        items = _bag_item_ids(emulator)
        if ItemId.POTION not in items:
            raise CeruleanChapterError(f"{label} lost its protected Potion.")
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        target = items.index(ItemId.POTION)
        if absolute == target:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if absolute < target else "up",
            timing.move_cursor_wait_frames,
        )
    else:
        raise CeruleanChapterError(f"{label} could not select its protected Potion.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.dialogue_wait_frames)

    for _ in range(6):
        if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) == 0:
            break
        _pulse(executor, MacroActionKind.MOVE, "up", timing.move_cursor_wait_frames)
    else:
        raise CeruleanChapterError(f"{label} could not select the party lead.")

    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    expected_healed_hp = min(before.first_party_max_hp, before.first_party_hp + 20)
    current = reader.read()
    saw_exact_heal = (
        current.first_party_hp == expected_healed_hp
        and _bag_quantity(emulator, ItemId.POTION) == expected_quantity
    )
    for _ in range(30):
        _wait(executor, timing.dialogue_wait_frames)
        current = reader.read()
        if current.first_party_hp == expected_healed_hp:
            saw_exact_heal = True
        if (
            saw_exact_heal
            and _bag_quantity(emulator, ItemId.POTION) == expected_quantity
            and current.battle_state == 2
            and (current.first_party_hp or 0) > 0
            and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
        ):
            selected_main = reader.read_battle_menu_state(current).selected_main_command
            if selected_main == 0:
                return
            restore_direction = {1: "up", 2: "left", 3: "up"}.get(selected_main)
            if restore_direction is None:
                raise CeruleanChapterError(
                    f"{label} exposed an invalid post-recovery MAIN cursor."
                )
            _pulse(
                executor,
                MacroActionKind.MOVE,
                restore_direction,
                timing.move_cursor_wait_frames,
            )
            continue
        if current.battle_state != 2 or (current.first_party_hp or 0) <= 0:
            raise CeruleanChapterError(f"{label} lost its living battle during recovery.")
        executor.execute(MacroAction(MacroActionKind.CANCEL))
    raise CeruleanChapterError(f"{label} missed its Potion or MAIN-menu recovery proof.")


def _obtain_helix_fossil(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    tracker: CeruleanProgressTracker,
    timing: CeruleanTiming,
) -> tuple[RawGameState, CeruleanChapterState]:
    for _ in range(timing.fossil_dialogue_pulses):
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
        raw = reader.read()
        evidence = reader.read_cerulean_chapter_state(raw)
        if evidence.fossil_snapshot:
            if (
                not evidence.got_helix_fossil
                or not evidence.helix_fossil_in_bag
                or evidence.got_dome_fossil
                or evidence.dome_fossil_in_bag
            ):
                raise CeruleanChapterError("The clean route selected the wrong fossil.")
            _observe_semantic(
                tracker,
                evidence,
                CeruleanPhase.FOSSIL_OBTAINED,
                "Helix Fossil",
            )
            return raw, evidence
    raise CeruleanChapterError("Helix Fossil failed its bounded semantic gate.")


def _observe_boundary(
    reader: PokemonRedStateReader,
    tracker: CeruleanProgressTracker,
    expected: CeruleanBoundary,
) -> tuple[RawGameState, CeruleanChapterState]:
    raw = reader.read()
    evidence = reader.read_cerulean_chapter_state(raw)
    if evidence.boundary is not expected:
        raise CeruleanChapterError(f"The clean run missed the {expected.value} boundary.")
    try:
        tracker.observe(evidence)
    except CeruleanProgressError as error:
        raise CeruleanChapterError(str(error)) from error
    return raw, evidence


def _observe_semantic(
    tracker: CeruleanProgressTracker,
    evidence: CeruleanChapterState,
    expected: CeruleanPhase,
    label: str,
) -> None:
    try:
        phase = tracker.observe(evidence)
    except CeruleanProgressError as error:
        raise CeruleanChapterError(str(error)) from error
    if phase is not expected:
        raise CeruleanChapterError(f"{label} failed its semantic phase gate.")


def _expect_route_3_victory(
    evidence: CeruleanChapterState,
    position: int,
) -> None:
    expected = tuple(index <= position for index in range(4))
    if (
        evidence.battle_state != 0
        or evidence.first_party_hp is None
        or evidence.first_party_hp <= 0
        or evidence.required_route_3_trainer_events != expected
    ):
        trainer_index = ROUTE_3_REQUIRED_TRAINER_INDEXES[position]
        raise CeruleanChapterError(
            f"Route 3 trainer {trainer_index} victory failed its event latch."
        )


def _route_3_victory_sequence(
    states: tuple[CeruleanChapterState, ...],
) -> bool:
    return len(states) == 4 and all(
        state.battle_state == 0
        and state.required_route_3_trainer_events == tuple(index <= position for index in range(4))
        for position, state in enumerate(states)
    )


def _reverse_directions(directions: tuple[str, ...]) -> tuple[str, ...]:
    opposite = {
        "up": "down",
        "down": "up",
        "left": "right",
        "right": "left",
    }
    return tuple(opposite[direction] for direction in reversed(directions))


def _expect_position(
    state: RawGameState,
    map_id: MapId,
    x: int,
    y: int,
    label: str,
) -> None:
    if (
        state.map_id != map_id
        or state.player_x != x
        or state.player_y != y
        or state.battle_state != 0
    ):
        raise CeruleanChapterError(f"The clean run missed the stable {label} gate.")


def _pp_at(raw: RawGameState, one_based_slot: int) -> int:
    pp = raw.first_party_pp or ()
    index = one_based_slot - 1
    return pp[index] & 0x3F if 0 <= index < len(pp) else 0


def _wait(executor: _CountingChapterExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _emit(
    sink: ProgressSink | None,
    emulator: EmulatorState,
    checkpoint_id: str,
    label: str,
    completed: int,
) -> None:
    if sink is not None:
        sink(
            CeruleanProgress(
                checkpoint_id=checkpoint_id,
                label=label,
                completed=completed,
                total=CERULEAN_CHECKPOINT_COUNT,
                frames_executed=emulator.frame_count,
            )
        )


def _public_state(state: RawGameState) -> dict[str, object]:
    return {
        "map_id": state.map_id,
        "player_x": state.player_x,
        "player_y": state.player_y,
        "party_count": state.party_count,
        "battle_state": state.battle_state,
        "level": state.first_party_level,
        "hp": state.first_party_hp,
        "max_hp": state.first_party_max_hp,
        "status": state.first_party_status,
    }
