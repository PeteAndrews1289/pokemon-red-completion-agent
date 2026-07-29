"""Deterministic post-Brock chapter through a verified Cerulean arrival.

The route and semantic gates are pinned to pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8``. The chapter continues the same
clean run used to qualify Brock. It never saves, restores, or reads revision
specific memory directly; all gates come from the observation adapter.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import (
    ROUTE_3_REQUIRED_TRAINER_SPECS,
    BattleMenuPhase,
    CeruleanBoundary,
    CeruleanChapterState,
    CeruleanPhase,
    CeruleanProgressError,
    CeruleanProgressTracker,
    MapId,
    PewterChapterState,
    PokemonRedStateReader,
    RawGameState,
)

CERULEAN_CHECKPOINT_COUNT = 15
ROUTE_3_REQUIRED_TRAINER_INDEXES = tuple(spec[0] for spec in ROUTE_3_REQUIRED_TRAINER_SPECS)
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
CENTER_HEAL_APPROACH_DIRECTIONS = ("up",) * 4
CENTER_EXIT_DIRECTIONS = ("down",) * 5
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
MT_MOON_1F_SEED_WAITS = ((14, 2), (34, 1), (35, 1), (78, 2), (100, 2))
MT_MOON_B1F_DIRECTIONS = _directions("R" * 2 + "D" * 11 + "R" * 14 + "D")
MT_MOON_B1F_SEED_WAITS = ((14, 1),)
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
MT_MOON_B2F_SEED_WAITS = ((19, 1), (29, 2), (65, 2))
ROCKET_TRIGGER_DIRECTIONS = ("up",)
ROCKET_TO_SUPER_NERD_DIRECTIONS = _directions("L" + "U" * 3 + "R" * 2 + "U" * 7 + "R" + "U")
SUPER_NERD_TO_HELIX_DIRECTIONS = ("up",)
MT_MOON_B2F_EXIT_DIRECTIONS = _directions("U" * 3 + "L" * 10 + "D" * 2 + "R" * 2 + "D")
MT_MOON_B1F_EXIT_DIRECTIONS = ("right",) * 4

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
            and self.saw_required_rocket_battle
            and self.rocket_battle_evidence.required_rocket_battle_snapshot
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
            },
            "mt_moon": {
                "required_rocket_battle_observed": self.saw_required_rocket_battle,
                "super_nerd_battle_observed": self.saw_super_nerd_battle,
                "helix_fossil_verified": self.fossil_evidence.fossil_snapshot
                and self.fossil_evidence.got_helix_fossil,
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

    _move(chapter_executor, reader, PEWTER_TO_CENTER_DIRECTIONS, "Pewter Center route")
    _wait(chapter_executor, timing.transition_wait_frames)
    _expect_position(reader.read(), MapId.PEWTER_POKECENTER, 3, 7, "Pewter Center")
    _heal(chapter_executor, reader, timing, MapId.PEWTER_POKECENTER, "Pewter Center")

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
            slot=3 if position == 0 else 1,
            label=f"Route 3 trainer {trainer_index}",
        )
        victory = _finish_battle(
            chapter_executor,
            reader,
            timing,
            MapId.ROUTE_3,
            f"Route 3 trainer {trainer_index}",
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
        _recover_at_pewter_center(
            chapter_executor,
            reader,
            timing,
            route_prefix,
        )

    _move(
        chapter_executor,
        reader,
        ROUTE_3_REMAINDER_DIRECTIONS,
        "Route 3 east route",
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

    _move_with_seed_waits(
        chapter_executor,
        reader,
        MT_MOON_1F_DIRECTIONS,
        MT_MOON_1F_SEED_WAITS,
        "Mt. Moon 1F legal route",
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

    _move_with_seed_waits(
        chapter_executor,
        reader,
        MT_MOON_B1F_DIRECTIONS,
        MT_MOON_B1F_SEED_WAITS,
        "Mt. Moon B1F legal route",
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

    _move_with_seed_waits(
        chapter_executor,
        reader,
        MT_MOON_B2F_TO_ROCKET_DIRECTIONS,
        MT_MOON_B2F_SEED_WAITS,
        "Mt. Moon Rocket approach",
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
        slot=4,
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
    if not rocket_victory_evidence.beat_required_rocket:
        raise CeruleanChapterError("The required Rocket event did not persist.")
    for _ in range(timing.rocket_cleanup_pulses):
        chapter_executor.execute(MacroAction(MacroActionKind.CANCEL))
        _wait(chapter_executor, timing.dialogue_wait_frames)

    _move(
        chapter_executor,
        reader,
        ROCKET_TO_SUPER_NERD_DIRECTIONS,
        "Super Nerd approach",
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
    )
    super_nerd_victory_evidence = reader.read_cerulean_chapter_state(super_nerd_defeated)
    if not super_nerd_victory_evidence.beat_super_nerd:
        raise CeruleanChapterError("The Super Nerd event did not persist.")

    _move(
        chapter_executor,
        reader,
        SUPER_NERD_TO_HELIX_DIRECTIONS,
        "Helix Fossil approach",
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

    _move(
        chapter_executor,
        reader,
        MT_MOON_B2F_EXIT_DIRECTIONS,
        "Mt. Moon B2F exit route",
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
    _wait(chapter_executor, timing.b1f_exit_seed_wait_frames)
    _move(
        chapter_executor,
        reader,
        MT_MOON_B1F_EXIT_DIRECTIONS,
        "Mt. Moon final exit",
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
            raise CeruleanChapterError(f"Squirtle's lineage fainted during {label}.")
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


def _heal(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CeruleanTiming,
    center_map: MapId,
    label: str,
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
    _move(executor, reader, CENTER_EXIT_DIRECTIONS, f"{label} exit")
    _wait(executor, timing.transition_wait_frames)
    return reader.read()


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
) -> None:
    initial = _pp_at(reader.read(), slot)
    if initial <= 0:
        raise CeruleanChapterError(f"{label} move slot {slot} had no usable PP.")

    for _ in range(timing.max_main_menu_pulses):
        raw = reader.read()
        if raw.battle_state != 2:
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

    for _ in range(timing.max_attack_start_pulses):
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.selected_move_wait_frames)
        if _pp_at(reader.read(), slot) < initial:
            return
        if reader.read().battle_state != 2:
            raise CeruleanChapterError(f"{label} ended before its persistent PP-decrement gate.")
    raise CeruleanChapterError(f"{label} failed its persistent PP-decrement gate.")


def _finish_battle(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CeruleanTiming,
    expected_map: MapId,
    label: str,
) -> RawGameState:
    saw_battle = False
    stable_reads = 0
    for _ in range(timing.max_battle_pulses):
        before = reader.read()
        if before.map_id != expected_map:
            raise CeruleanChapterError(f"{label} left its expected map.")
        if before.battle_state not in {0, 2}:
            raise CeruleanChapterError(f"{label} changed to an unexpected battle type.")
        saw_battle = saw_battle or before.battle_state == 2
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
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
