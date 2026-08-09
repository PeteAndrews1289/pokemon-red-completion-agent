"""Deterministic post-Pokédex chapter through a verified Brock victory.

The route and semantic gates are pinned to pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8``. The chapter starts at the
already-qualified Pokédex boundary and runs without saves or restoration.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import (
    BUBBLE_MOVE_ID,
    ItemId,
    MapId,
    NorthboundPhase,
    OaksErrandState,
    PewterChapterState,
    PewterProgressError,
    PewterProgressTracker,
    PokemonRedStateReader,
    RawGameState,
    TravelBoundary,
)
from pokemon_red_completion.route_1_wild import (
    Route1WildFleeEvidence,
    move_route_1_with_wild_flees,
)

PEWTER_CHECKPOINT_COUNT = 10

LAB_TO_PALLET_DIRECTIONS = ("down",) * 9
PALLET_TO_ROUTE_1_DIRECTIONS = (
    *(("left",) * 3),
    *(("up",) * 10),
    "right",
    *(("up",) * 3),
)
ROUTE_1_TO_VIRIDIAN_DIRECTIONS = (
    *(("up",) * 7),
    *(("left",) * 2),
    *(("up",) * 4),
    *(("right",) * 4),
    *(("up",) * 4),
    *(("left",) * 3),
    *(("up",) * 6),
    *(("right",) * 5),
    *(("up",) * 12),
    *(("left",) * 3),
    *(("up",) * 3),
)
VIRIDIAN_TO_ROUTE_2_DIRECTIONS = (
    *(("up",) * 5),
    "left",
    *(("up",) * 2),
    "left",
    *(("up",) * 26),
    "left",
    *(("up",) * 3),
)
ROUTE_2_TO_FOREST_GATE_DIRECTIONS = (
    *(("up",) * 9),
    "left",
    *(("up",) * 5),
    *(("left",) * 2),
    "up",
    "left",
    *(("up",) * 7),
    *(("right",) * 3),
    "up",
    *(("right",) * 2),
    *(("up",) * 4),
    *(("left",) * 6),
    "up",
)
FOREST_GATE_TO_FOREST_DIRECTIONS = (
    *(("up",) * 6),
    "right",
    "up",
)
FOREST_ROUTE_DIRECTIONS = tuple(
    {
        "U": "up",
        "D": "down",
        "L": "left",
        "R": "right",
    }[direction]
    for direction in (
        "L"
        + "U" * 3
        + "R"
        + "U"
        + "R"
        + "U" * 2
        + "R" * 7
        + "U" * 29
        + "R"
        + "U" * 3
        + "L" * 8
        + "D" * 7
        + "L" * 5
        + "U" * 13
        + "L" * 5
        + "D" * 19
        + "L" * 6
        + "U" * 3
        + "L"
        + "U" * 19
    )
)
FOREST_NORTH_GATE_EXIT_DIRECTIONS = (
    *(("up",) * 6),
    "right",
    "up",
)
ROUTE_2_TO_PEWTER_PREFIX_DIRECTIONS = ("up",) * 9
ROUTE_2_TO_PEWTER_SUFFIX_DIRECTIONS = (
    *(("right",) * 5),
    *(("up",) * 3),
)
PEWTER_TO_GYM_DIRECTIONS = (
    *(("up",) * 13),
    "right",
    *(("up",) * 9),
    *(("left",) * 8),
    *(("down",) * 3),
    "left",
    *(("down",) * 2),
    *(("right",) * 6),
    "up",
)
GYM_TO_BROCK_DIRECTIONS = (
    *(("up",) * 5),
    *(("left",) * 3),
    *(("up",) * 4),
    *(("right",) * 3),
    *(("up",) * 2),
)


class PewterChapterError(RuntimeError):
    """Raised when the bounded post-Pokédex chapter misses a verified gate."""


class ActionExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class EmulatorState(Protocol):
    frame_count: int

    @property
    def pressed_buttons(self) -> frozenset[str]: ...


@dataclass(frozen=True, slots=True)
class PewterTiming:
    transition_wait_frames: int = 120
    route_1_seed_wait_frames: int = 6
    route_1_wild_exit_stabilization_frames: int = 120
    encounter_wait_frames: int = 240
    battle_wait_frames: int = 180
    dialogue_wait_frames: int = 240
    first_kakuna_seed_wait_frames: int = 467
    second_kakuna_seed_wait_frames: int = 420
    third_kakuna_seed_wait_frames: int = 2
    forest_exit_seed_wait_frames: int = 2
    pewter_seed_wait_frames: int = 1
    fight_menu_wait_frames: int = 120
    move_cursor_wait_frames: int = 60
    selected_move_wait_frames: int = 600
    final_stability_wait_frames: int = 1
    max_battle_pulses: int = 120
    max_trainer_intro_pulses: int = 12
    max_attack_start_pulses: int = 20
    brock_setup_pulses: int = 3
    max_brock_battle_pulses: int = 100
    max_brock_reward_pulses: int = 40
    max_control_release_pulses: int = 10
    max_route_1_wild_flees: int = 8

    def __post_init__(self) -> None:
        for name, value in (
            (name, getattr(self, name))
            for name in self.__dataclass_fields__
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_PEWTER_TIMING = PewterTiming()


@dataclass(frozen=True, slots=True)
class PewterProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[PewterProgress], None]


@dataclass(frozen=True, slots=True)
class PewterChapterReport:
    pokedex_evidence: OaksErrandState
    lab_exited: RawGameState
    viridian_reached: RawGameState
    route_2_reached: RawGameState
    forest_gate_reached: RawGameState
    forest_entered: RawGameState
    forest_cleared: RawGameState
    pewter_reached: RawGameState
    gym_entered: RawGameState
    brock_battle: RawGameState
    brock_defeated: RawGameState
    gym_entry_evidence: PewterChapterState
    brock_battle_evidence: PewterChapterState
    brock_victory_evidence: PewterChapterState
    reached_boundaries: tuple[TravelBoundary, ...]
    saw_brock_battle: bool
    route_1_wild_flees: tuple[Route1WildFleeEvidence, ...]
    overworld_control_verified: bool
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            self.pokedex_evidence.pokedex_snapshot
            and self.reached_boundaries
            == tuple(
                boundary
                for boundary in TravelBoundary
                if boundary is not TravelBoundary.UNKNOWN
            )
            and self.gym_entry_evidence.brock_ready_snapshot
            and self.saw_brock_battle
            and all(item.verified for item in self.route_1_wild_flees)
            and self.brock_battle_evidence.brock_battle_snapshot
            and self.brock_victory_evidence.brock_victory_snapshot
            and self.overworld_control_verified
            and self.brock_defeated.first_party_level is not None
            and self.brock_defeated.first_party_hp is not None
            and self.brock_defeated.first_party_hp > 0
            and self.brock_defeated.first_party_status == 0
            and ItemId.TM34_BIDE in set(self.brock_defeated.bag_item_ids or ())
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return (
            ("lab_exited", "Exited Oak's Lab after receiving the Pokédex", self.lab_exited),
            ("viridian_northbound", "Reached Viridian City northbound", self.viridian_reached),
            ("route_2_reached", "Reached Route 2", self.route_2_reached),
            (
                "forest_gate_reached",
                "Reached the Viridian Forest gate",
                self.forest_gate_reached,
            ),
            ("forest_entered", "Entered Viridian Forest", self.forest_entered),
            ("forest_cleared", "Cleared Viridian Forest", self.forest_cleared),
            ("pewter_reached", "Reached Pewter City", self.pewter_reached),
            ("pewter_gym_entered", "Entered Pewter Gym battle-ready", self.gym_entered),
            ("brock_battle", "Verified the live Brock battle", self.brock_battle),
            ("brock_defeated", "Defeated Brock and received TM34", self.brock_defeated),
        )

    def public_dict(self) -> dict[str, object]:
        bubble_pp = _move_pp(self.brock_defeated, BUBBLE_MOVE_ID)
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
                "ordered_boundaries_total": len(TravelBoundary) - 1,
                "brock_battle_observed": self.saw_brock_battle,
                "route_1_wild_flees": [
                    item.public_dict() for item in self.route_1_wild_flees
                ],
            },
            "brock": {
                "victory_verified": self.brock_victory_evidence.brock_victory_snapshot,
                "boulder_badge_verified": (
                    self.brock_victory_evidence.boulder_badge
                    and self.brock_victory_evidence.boulder_badge_mirror
                ),
                "tm34_verified": (
                    self.brock_victory_evidence.got_tm34
                    and self.brock_victory_evidence.tm34_in_bag
                ),
                "overworld_control_verified": self.overworld_control_verified,
                "squirtle_level": self.brock_defeated.first_party_level,
                "squirtle_hp": self.brock_defeated.first_party_hp,
                "squirtle_max_hp": self.brock_defeated.first_party_max_hp,
                "squirtle_status": self.brock_defeated.first_party_status,
                "bubble_pp": bubble_pp,
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


def run_pewter_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ActionExecutor,
    *,
    timing: PewterTiming = DEFAULT_PEWTER_TIMING,
    progress: ProgressSink | None = None,
) -> PewterChapterReport:
    """Continue one clean run from the verified Pokédex gate through Brock."""
    start_frames = emulator.frame_count
    chapter_executor = _CountingChapterExecutor(executor)
    starting_raw = reader.read()
    pokedex_evidence = reader.read_oaks_errand_state(starting_raw)
    try:
        tracker = PewterProgressTracker(pokedex_evidence)
    except PewterProgressError as error:
        raise PewterChapterError(str(error)) from error

    _move(chapter_executor, reader, LAB_TO_PALLET_DIRECTIONS, "Oak's Lab exit")
    _wait(chapter_executor, timing.transition_wait_frames)
    lab_exited, _ = _observe_boundary(
        reader,
        tracker,
        TravelBoundary.PALLET_LAB_EXTERIOR,
    )
    _emit(progress, emulator, "lab_exited", "Exited Oak's Lab after the Pokédex", 1)

    _move(chapter_executor, reader, PALLET_TO_ROUTE_1_DIRECTIONS, "Pallet north route")
    _wait(chapter_executor, timing.transition_wait_frames)
    _expect_position(reader.read(), MapId.ROUTE_1, 10, 35, "Route 1 south entrance")
    _wait(chapter_executor, timing.route_1_seed_wait_frames)
    _, route_1_wild_flees = _move_route_1_with_wild_flees(
        chapter_executor,
        reader,
        ROUTE_1_TO_VIRIDIAN_DIRECTIONS,
        "Route 1 northbound",
        maximum_flees=timing.max_route_1_wild_flees,
        stabilization_frames=timing.route_1_wild_exit_stabilization_frames,
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    viridian_reached, _ = _observe_boundary(
        reader,
        tracker,
        TravelBoundary.VIRIDIAN_SOUTH_EDGE,
    )
    _emit(progress, emulator, "viridian_northbound", "Reached Viridian City northbound", 2)

    _move(chapter_executor, reader, VIRIDIAN_TO_ROUTE_2_DIRECTIONS, "Viridian north route")
    _wait(chapter_executor, timing.transition_wait_frames)
    route_2_reached, _ = _observe_boundary(
        reader,
        tracker,
        TravelBoundary.ROUTE_2_SOUTH_EDGE,
    )
    _emit(progress, emulator, "route_2_reached", "Reached Route 2", 3)

    _move(
        chapter_executor,
        reader,
        ROUTE_2_TO_FOREST_GATE_DIRECTIONS,
        "Route 2 forest-gate route",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    forest_gate_reached, _ = _observe_boundary(
        reader,
        tracker,
        TravelBoundary.FOREST_SOUTH_GATE,
    )
    _emit(progress, emulator, "forest_gate_reached", "Reached Viridian Forest gate", 4)

    _move(
        chapter_executor,
        reader,
        FOREST_GATE_TO_FOREST_DIRECTIONS,
        "Viridian Forest entrance",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    forest_entered, _ = _observe_boundary(
        reader,
        tracker,
        TravelBoundary.FOREST_SOUTH_ENTRY,
    )
    _emit(progress, emulator, "forest_entered", "Entered Viridian Forest", 5)

    _move(chapter_executor, reader, FOREST_ROUTE_DIRECTIONS[:90], "forest training route")
    _trigger_wild_battle(
        chapter_executor,
        reader,
        "down",
        timing.first_kakuna_seed_wait_frames,
        timing,
        "first Kakuna",
    )
    _finish_battle(
        chapter_executor,
        reader,
        expected_battle_state=1,
        max_pulses=timing.max_battle_pulses,
        timing=timing,
        label="first Kakuna",
    )
    _expect_party(reader.read(), level=7, minimum_hp=1, label="first Kakuna")

    _move(chapter_executor, reader, ("down",) * 2, "second Kakuna approach")
    _trigger_wild_battle(
        chapter_executor,
        reader,
        "down",
        timing.second_kakuna_seed_wait_frames,
        timing,
        "second Kakuna",
    )
    _finish_battle(
        chapter_executor,
        reader,
        expected_battle_state=1,
        max_pulses=timing.max_battle_pulses,
        timing=timing,
        label="second Kakuna",
    )
    _expect_party(reader.read(), level=7, minimum_hp=1, label="second Kakuna")

    _move(chapter_executor, reader, ("down",) * 2, "third Kakuna approach")
    _trigger_wild_battle(
        chapter_executor,
        reader,
        "down",
        timing.third_kakuna_seed_wait_frames,
        timing,
        "third Kakuna",
    )
    _finish_battle(
        chapter_executor,
        reader,
        expected_battle_state=1,
        max_pulses=timing.max_battle_pulses,
        timing=timing,
        label="third Kakuna",
    )
    _expect_party(
        reader.read(),
        level=8,
        minimum_hp=1,
        required_move=BUBBLE_MOVE_ID,
        label="third Kakuna",
    )

    _move(
        chapter_executor,
        reader,
        FOREST_ROUTE_DIRECTIONS[97:117],
        "mandatory Bug Catcher approach",
    )
    _enter_trainer_battle(
        chapter_executor,
        reader,
        timing,
        MapId.VIRIDIAN_FOREST,
        "Viridian Forest Bug Catcher",
    )
    _advance_until_pp_decreases(
        chapter_executor,
        reader,
        timing,
        move_slot=0,
        label="Bug Catcher opening Tackle",
    )
    _select_third_move(chapter_executor, reader, timing, "Bug Catcher Bubble")
    _finish_battle(
        chapter_executor,
        reader,
        expected_battle_state=2,
        max_pulses=timing.max_battle_pulses,
        timing=timing,
        label="Viridian Forest Bug Catcher",
    )
    _expect_brock_party_ready(reader.read(), "Viridian Forest exit")

    _move(chapter_executor, reader, ("up",) * 5, "forest north route prefix")
    _wait(chapter_executor, timing.forest_exit_seed_wait_frames)
    _move(chapter_executor, reader, ("up",) * 13, "forest north route")
    _move(chapter_executor, reader, ("up",), "forest north-gate transition")
    _wait(chapter_executor, timing.transition_wait_frames)
    forest_cleared, _ = _observe_boundary(
        reader,
        tracker,
        TravelBoundary.FOREST_NORTH_GATE,
    )
    _emit(progress, emulator, "forest_cleared", "Cleared Viridian Forest", 6)

    _move(
        chapter_executor,
        reader,
        FOREST_NORTH_GATE_EXIT_DIRECTIONS,
        "Viridian Forest north-gate exit",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _observe_boundary(reader, tracker, TravelBoundary.ROUTE_2_NORTH_RETURN)

    _move(
        chapter_executor,
        reader,
        ROUTE_2_TO_PEWTER_PREFIX_DIRECTIONS,
        "upper Route 2 prefix",
    )
    _wait(chapter_executor, timing.pewter_seed_wait_frames)
    _move(
        chapter_executor,
        reader,
        ROUTE_2_TO_PEWTER_SUFFIX_DIRECTIONS,
        "upper Route 2 to Pewter",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    pewter_reached, _ = _observe_boundary(
        reader,
        tracker,
        TravelBoundary.PEWTER_SOUTH_EDGE,
    )
    _emit(progress, emulator, "pewter_reached", "Reached Pewter City", 7)

    _move(chapter_executor, reader, PEWTER_TO_GYM_DIRECTIONS, "Pewter Gym route")
    _wait(chapter_executor, timing.transition_wait_frames)
    gym_entered, gym_entry_evidence = _observe_boundary(
        reader,
        tracker,
        TravelBoundary.PEWTER_GYM_ENTRANCE,
    )
    _emit(progress, emulator, "pewter_gym_entered", "Entered Pewter Gym battle-ready", 8)

    _move(chapter_executor, reader, GYM_TO_BROCK_DIRECTIONS, "Brock approach")
    _expect_position(reader.read(), MapId.PEWTER_GYM, 4, 2, "Brock approach")
    chapter_executor.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(chapter_executor, timing.dialogue_wait_frames)
    brock_battle = _enter_trainer_battle(
        chapter_executor,
        reader,
        timing,
        MapId.PEWTER_GYM,
        "Brock",
    )
    brock_battle_evidence = reader.read_pewter_chapter_state(brock_battle)
    try:
        phase = tracker.observe(brock_battle_evidence)
    except PewterProgressError as error:
        raise PewterChapterError(str(error)) from error
    if phase is not NorthboundPhase.BROCK_BATTLE:
        raise PewterChapterError("The live Brock identity failed its semantic gate.")
    _emit(progress, emulator, "brock_battle", "Verified the live Brock battle", 9)

    for _ in range(timing.brock_setup_pulses):
        chapter_executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(chapter_executor, timing.dialogue_wait_frames)
    _select_third_move(chapter_executor, reader, timing, "Brock Bubble")
    _finish_battle(
        chapter_executor,
        reader,
        expected_battle_state=2,
        max_pulses=timing.max_brock_battle_pulses,
        timing=timing,
        label="Brock",
    )
    _, first_victory = _finish_brock_rewards(
        chapter_executor,
        reader,
        tracker,
        timing,
    )
    brock_defeated, brock_victory_evidence = _release_and_probe_overworld_control(
        chapter_executor,
        reader,
        timing,
    )
    if not first_victory.brock_victory_snapshot:
        raise PewterChapterError("Brock victory disappeared before control restoration.")
    try:
        tracker.observe(brock_victory_evidence)
    except PewterProgressError as error:
        raise PewterChapterError(str(error)) from error
    _emit(progress, emulator, "brock_defeated", "Defeated Brock and received TM34", 10)

    report = PewterChapterReport(
        pokedex_evidence=pokedex_evidence,
        lab_exited=lab_exited,
        viridian_reached=viridian_reached,
        route_2_reached=route_2_reached,
        forest_gate_reached=forest_gate_reached,
        forest_entered=forest_entered,
        forest_cleared=forest_cleared,
        pewter_reached=pewter_reached,
        gym_entered=gym_entered,
        brock_battle=brock_battle,
        brock_defeated=brock_defeated,
        gym_entry_evidence=gym_entry_evidence,
        brock_battle_evidence=brock_battle_evidence,
        brock_victory_evidence=brock_victory_evidence,
        reached_boundaries=tracker.reached_boundaries,
        saw_brock_battle=tracker.saw_brock_battle,
        route_1_wild_flees=route_1_wild_flees,
        overworld_control_verified=True,
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=chapter_executor.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise PewterChapterError("The Brock chapter failed its public evidence contract.")
    return report


def _move(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    label: str,
) -> RawGameState:
    state = reader.read()
    for step, direction in enumerate(directions, start=1):
        if state.battle_state:
            raise PewterChapterError(
                f"Unexpected battle interrupted {label} before step {step}."
            )
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        state = reader.read()
        if state.battle_state:
            raise PewterChapterError(
                f"Unexpected battle interrupted {label} at step {step}."
            )
        if state.first_party_hp == 0:
            raise PewterChapterError(f"Squirtle fainted during {label}.")
    return state


def _move_route_1_with_wild_flees(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    label: str,
    *,
    maximum_flees: int,
    stabilization_frames: int,
) -> tuple[RawGameState, tuple[Route1WildFleeEvidence, ...]]:
    return move_route_1_with_wild_flees(
        executor,
        reader,
        directions,
        label,
        maximum_flees=maximum_flees,
        stabilization_frames=stabilization_frames,
        error_type=PewterChapterError,
    )


def _trigger_wild_battle(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    direction: str,
    seed_wait_frames: int,
    timing: PewterTiming,
    label: str,
) -> RawGameState:
    _wait(executor, seed_wait_frames)
    if reader.read().battle_state:
        raise PewterChapterError(f"{label} began before its intentional trigger.")
    executor.execute(MacroAction(MacroActionKind.MOVE, direction))
    _wait(executor, timing.encounter_wait_frames)
    raw = reader.read()
    if raw.battle_state != 1:
        raise PewterChapterError(f"{label} failed its expected wild-battle gate.")
    return raw


def _enter_trainer_battle(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: PewterTiming,
    expected_map: MapId,
    label: str,
) -> RawGameState:
    for _ in range(timing.max_trainer_intro_pulses):
        raw = reader.read()
        if raw.battle_state == 1:
            raise PewterChapterError(f"Unexpected wild battle replaced {label}.")
        if raw.battle_state == 2:
            return raw
        if raw.map_id != expected_map:
            raise PewterChapterError(f"{label} left its expected map before battle.")
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    raise PewterChapterError(f"{label} failed its bounded trainer-battle gate.")


def _advance_until_pp_decreases(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: PewterTiming,
    *,
    move_slot: int,
    label: str,
) -> None:
    initial = _pp_at(reader.read(), move_slot)
    if initial <= 0:
        raise PewterChapterError(f"{label} had no usable PP.")
    for _ in range(timing.max_attack_start_pulses):
        raw = reader.read()
        if raw.battle_state != 2:
            raise PewterChapterError(f"{label} left the trainer battle too early.")
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
        if _pp_at(reader.read(), move_slot) < initial:
            return
    raise PewterChapterError(f"{label} failed its bounded PP-decrement gate.")


def _select_third_move(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: PewterTiming,
    label: str,
) -> None:
    before = _move_pp(reader.read(), BUBBLE_MOVE_ID)
    if before is None or before < 1:
        raise PewterChapterError(f"{label} was unavailable.")
    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    _wait(executor, timing.fight_menu_wait_frames)
    executor.execute(MacroAction(MacroActionKind.MOVE, "down"))
    _wait(executor, timing.move_cursor_wait_frames)
    executor.execute(MacroAction(MacroActionKind.MOVE, "down"))
    _wait(executor, timing.move_cursor_wait_frames)
    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    _wait(executor, timing.selected_move_wait_frames)
    after = _move_pp(reader.read(), BUBBLE_MOVE_ID)
    if after is None or after >= before:
        raise PewterChapterError(f"{label} failed its persistent Bubble-PP gate.")


def _finish_battle(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    *,
    expected_battle_state: int,
    max_pulses: int,
    timing: PewterTiming,
    label: str,
) -> RawGameState:
    saw_expected_battle = False
    stable_reads = 0
    for _ in range(max_pulses):
        before = reader.read()
        if before.battle_state not in {0, expected_battle_state}:
            raise PewterChapterError(f"{label} changed to an unexpected battle type.")
        saw_expected_battle = saw_expected_battle or (
            before.battle_state == expected_battle_state
        )
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(
            executor,
            timing.battle_wait_frames
            if before.battle_state
            else timing.dialogue_wait_frames,
        )
        after = reader.read()
        if after.first_party_hp == 0:
            raise PewterChapterError(f"Squirtle fainted during {label}.")
        if after.battle_state not in {0, expected_battle_state}:
            raise PewterChapterError(f"{label} changed to an unexpected battle type.")
        saw_expected_battle = saw_expected_battle or (
            after.battle_state == expected_battle_state
        )
        if (
            saw_expected_battle
            and after.battle_state == 0
            and reader.read_input_readiness().ready
        ):
            stable_reads += 1
            if stable_reads >= 2:
                return after
        else:
            stable_reads = 0
    raise PewterChapterError(f"{label} failed its bounded battle-completion gate.")


def _finish_brock_rewards(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    tracker: PewterProgressTracker,
    timing: PewterTiming,
) -> tuple[RawGameState, PewterChapterState]:
    for _ in range(timing.max_brock_reward_pulses):
        raw = reader.read()
        state = reader.read_pewter_chapter_state(raw)
        if state.brock_victory_snapshot:
            try:
                tracker.observe(state)
            except PewterProgressError as error:
                raise PewterChapterError(str(error)) from error
            return raw, state
        if raw.map_id != MapId.PEWTER_GYM or raw.battle_state:
            raise PewterChapterError("Brock rewards left the stable Gym dialogue path.")
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    raise PewterChapterError("Brock rewards failed their bounded semantic gate.")


def _release_and_probe_overworld_control(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: PewterTiming,
) -> tuple[RawGameState, PewterChapterState]:
    """Clear residual reward text and prove that an overworld move is accepted."""
    for _ in range(timing.max_control_release_pulses):
        before = reader.read()
        evidence = reader.read_pewter_chapter_state(before)
        if not evidence.brock_victory_snapshot:
            raise PewterChapterError(
                "Brock evidence changed while restoring overworld control."
            )
        if before.map_id != MapId.PEWTER_GYM or before.player_x != 4:
            raise PewterChapterError("Brock control probe left the expected Gym column.")

        executor.execute(MacroAction(MacroActionKind.MOVE, "down"))
        after = reader.read()
        if (
            after.map_id == MapId.PEWTER_GYM
            and after.player_x == before.player_x
            and after.player_y == (before.player_y or 0) + 1
        ):
            _wait(executor, timing.final_stability_wait_frames)
            stable = reader.read()
            stable_evidence = reader.read_pewter_chapter_state(stable)
            if (
                stable.player_x != after.player_x
                or stable.player_y != after.player_y
                or not stable_evidence.brock_victory_snapshot
            ):
                raise PewterChapterError(
                    "Post-Brock overworld control did not remain stable."
                )
            return stable, stable_evidence
        if (
            after.map_id != before.map_id
            or after.player_x != before.player_x
            or after.player_y != before.player_y
        ):
            raise PewterChapterError("Brock control probe moved to an unexpected state.")
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    raise PewterChapterError("Brock reward text failed the bounded movement-control probe.")


def _observe_boundary(
    reader: PokemonRedStateReader,
    tracker: PewterProgressTracker,
    expected: TravelBoundary,
) -> tuple[RawGameState, PewterChapterState]:
    raw = reader.read()
    state = reader.read_pewter_chapter_state(raw)
    if state.boundary is not expected:
        raise PewterChapterError(f"The clean run missed the {expected.value} boundary.")
    try:
        tracker.observe(state)
    except PewterProgressError as error:
        raise PewterChapterError(str(error)) from error
    return raw, state


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
        raise PewterChapterError(f"The clean run missed the stable {label} gate.")


def _expect_party(
    raw: RawGameState,
    *,
    level: int,
    minimum_hp: int,
    label: str,
    required_move: int | None = None,
) -> None:
    if (
        raw.party_count != 1
        or raw.first_party_level != level
        or (raw.first_party_hp or 0) < minimum_hp
        or raw.first_party_status != 0
        or (
            required_move is not None
            and required_move not in set(raw.first_party_moves or ())
        )
    ):
        raise PewterChapterError(f"{label} failed its persistent party-state gate.")


def _expect_brock_party_ready(raw: RawGameState, label: str) -> None:
    bubble_pp = _move_pp(raw, BUBBLE_MOVE_ID)
    if (
        raw.party_count != 1
        or raw.first_party_level != 9
        or (raw.first_party_hp or 0) < 19
        or raw.first_party_status != 0
        or bubble_pp is None
        or bubble_pp < 4
    ):
        raise PewterChapterError(f"{label} failed the Brock-readiness party gate.")


def _move_pp(raw: RawGameState, move_id: int) -> int | None:
    moves = raw.first_party_moves or ()
    pp = raw.first_party_pp or ()
    try:
        slot = moves.index(move_id)
    except ValueError:
        return None
    return _pp_at(raw, slot) if slot < len(pp) else None


def _pp_at(raw: RawGameState, slot: int) -> int:
    pp = raw.first_party_pp or ()
    return pp[slot] & 0x3F if 0 <= slot < len(pp) else 0


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
            PewterProgress(
                checkpoint_id=checkpoint_id,
                label=label,
                completed=completed,
                total=PEWTER_CHECKPOINT_COUNT,
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
