"""One clean, bounded run through the latest independently qualified objective.

The route and semantic gates in this module are pinned to pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8``. It composes the opening, lab
rival, Oak's Parcel, Pokédex, Viridian Forest, Brock, Mt. Moon, Bill, and Misty
chapters in one emulator session. It intentionally stops after the latest
repeat-qualified boundary; it is not a game-completion or learned-policy claim.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING, NewGameTiming
from pokemon_red_completion.cascade import (
    CASCADE_CHECKPOINT_COUNT,
    CascadeChapterError,
    CascadeChapterReport,
    CascadeProgress,
    run_cascade_chapter,
)
from pokemon_red_completion.cerulean import (
    CERULEAN_CHECKPOINT_COUNT,
    CeruleanChapterError,
    CeruleanChapterReport,
    CeruleanProgress,
    run_cerulean_chapter,
)
from pokemon_red_completion.domain import GameState
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import ExecutedAction, FrameSafeExecutor
from pokemon_red_completion.observation import (
    MapId,
    OaksErrandPhase,
    OaksErrandState,
    PokemonRedStateReader,
    RawGameState,
    game_mode,
    location_label,
    semantic_facts,
)
from pokemon_red_completion.opening import (
    DEFAULT_OPENING_TIMING,
    OPENING_CHECKPOINT_COUNT,
    OpeningChapterReport,
    OpeningProgress,
    OpeningTiming,
    run_opening_chapter,
)
from pokemon_red_completion.pewter import (
    PEWTER_CHECKPOINT_COUNT,
    PewterChapterError,
    PewterChapterReport,
    PewterProgress,
    run_pewter_chapter,
)
from pokemon_red_completion.rom import RomFingerprint
from pokemon_red_completion.route import COMPLETION_QUEST

POKEDEX_CHECKPOINT_COUNT = 11
QUALIFIED_PLAY_CHECKPOINT_COUNT = (
    POKEDEX_CHECKPOINT_COUNT
    + PEWTER_CHECKPOINT_COUNT
    + CERULEAN_CHECKPOINT_COUNT
    + CASCADE_CHECKPOINT_COUNT
)
QUALIFIED_THROUGH_OBJECTIVE = "defeat_misty"

LAB_RIVAL_TRIGGER_DIRECTIONS = ("down", "left", "left", "left", "down")
LAB_EXIT_DIRECTIONS = ("down",) * 6
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
VIRIDIAN_TO_MART_DIRECTIONS = (
    *(("up",) * 5),
    "left",
    *(("up",) * 2),
    "left",
    *(("up",) * 8),
    *(("right",) * 10),
    "up",
)
MART_EXIT_DIRECTIONS = ("right", "down", "down", "down")
VIRIDIAN_TO_ROUTE_1_DIRECTIONS = (
    *(("left",) * 10),
    *(("down",) * 8),
    "right",
    *(("down",) * 2),
    "right",
    *(("down",) * 6),
)
ROUTE_1_TO_PALLET_DIRECTIONS = (
    *(("down",) * 2),
    *(("right",) * 3),
    *(("down",) * 12),
    *(("left",) * 5),
    *(("down",) * 6),
    *(("right",) * 3),
    *(("down",) * 4),
    *(("left",) * 4),
    *(("down",) * 4),
    *(("right",) * 2),
    *(("down",) * 8),
)
PALLET_TO_LAB_DIRECTIONS = (
    *(("down",) * 2),
    "left",
    *(("down",) * 10),
    *(("right",) * 3),
    "up",
)
LAB_TO_OAK_DIRECTIONS = ("left", *(("up",) * 6), "right", "up", "up")


class QualifiedPlayError(RuntimeError):
    """Raised when the clean run misses a bounded route or semantic gate."""


@dataclass(frozen=True, slots=True)
class QualifiedPlayTiming:
    transition_wait_frames: int = 120
    rival_trigger_wait_frames: int = 360
    battle_wait_frames: int = 180
    dialogue_wait_frames: int = 240
    route_1_north_seed_wait_frames: int = 192
    mart_prompt_wait_frames: int = 240
    route_1_south_seed_wait_frames: int = 48
    max_rival_pulses: int = 56
    max_parcel_pulses: int = 5
    max_pokedex_pulses: int = 42

    def __post_init__(self) -> None:
        for name, value in (
            ("transition_wait_frames", self.transition_wait_frames),
            ("rival_trigger_wait_frames", self.rival_trigger_wait_frames),
            ("battle_wait_frames", self.battle_wait_frames),
            ("dialogue_wait_frames", self.dialogue_wait_frames),
            ("route_1_north_seed_wait_frames", self.route_1_north_seed_wait_frames),
            ("mart_prompt_wait_frames", self.mart_prompt_wait_frames),
            ("route_1_south_seed_wait_frames", self.route_1_south_seed_wait_frames),
            ("max_rival_pulses", self.max_rival_pulses),
            ("max_parcel_pulses", self.max_parcel_pulses),
            ("max_pokedex_pulses", self.max_pokedex_pulses),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_QUALIFIED_PLAY_TIMING = QualifiedPlayTiming()


@dataclass(frozen=True, slots=True)
class QualifiedPlayProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[QualifiedPlayProgress], None]


@dataclass(frozen=True, slots=True)
class QualifiedPlayReport:
    rom: RomFingerprint
    pyboy_version: str
    emulator_window: str
    emulator_speed: int
    opening: OpeningChapterReport
    rival_defeated: RawGameState
    viridian_reached: RawGameState
    parcel_received: RawGameState
    pallet_returned: RawGameState
    pokedex_received: RawGameState
    pewter: PewterChapterReport
    cerulean: CeruleanChapterReport
    cascade: CascadeChapterReport
    rival_evidence: OaksErrandState
    parcel_evidence: OaksErrandState
    pokedex_evidence: OaksErrandState
    saw_trainer_battle: bool
    facts: frozenset[str]
    verified_objectives: tuple[str, ...]
    next_objective: str | None
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            self.opening.passed
            and is_rival_victory_verified(
                self.rival_evidence,
                saw_trainer_battle=self.saw_trainer_battle,
            )
            and is_parcel_verified(self.parcel_evidence)
            and is_pokedex_verified(self.pokedex_evidence)
            and self.pewter.passed
            and self.cerulean.passed
            and self.cascade.passed
            and QUALIFIED_THROUGH_OBJECTIVE in self.verified_objectives
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        checkpoints = (
            (
                "bedroom_ready",
                "Bedroom input ready",
                self.opening.bedroom,
            ),
            (
                "downstairs",
                "Reached Red's house first floor",
                self.opening.downstairs,
            ),
            ("outside", "Exited into Pallet Town", self.opening.outside),
            ("oak_triggered", "Triggered Professor Oak", self.opening.oak_triggered),
            (
                "selection_ready",
                "Reached the starter selection gate",
                self.opening.selection_ready,
            ),
            (
                "starter_obtained",
                "Selected and verified Squirtle",
                self.opening.starter,
            ),
            ("rival_defeated", "Defeated the lab rival", self.rival_defeated),
            ("viridian_reached", "Reached Viridian City", self.viridian_reached),
            ("parcel_received", "Received Oak's Parcel", self.parcel_received),
            ("pallet_returned", "Returned safely to Pallet Town", self.pallet_returned),
            (
                "pokedex_received",
                "Delivered the parcel and received the Pokédex",
                self.pokedex_received,
            ),
            *self.pewter.checkpoints(),
            *self.cerulean.checkpoints(),
            *self.cascade.checkpoints(),
        )
        pewter = self.pewter.public_dict()
        return {
            "schema": "qualified-play-v4",
            "status": "ok" if self.passed else "failed",
            "qualified_through": QUALIFIED_THROUGH_OBJECTIVE,
            "game_complete": False,
            "safe_stop_reason": "latest_qualified_boundary",
            "rom": self.rom.public_dict(),
            "emulator": {
                "name": "PyBoy",
                "version": self.pyboy_version,
                "window": self.emulator_window,
                "speed": self.emulator_speed,
                "human_input": False,
                "save_on_exit": False,
            },
            "clean_power_on": self.opening.clean_power_on,
            "checkpoints": [
                {
                    "id": checkpoint_id,
                    "label": label,
                    "status": "verified",
                    "state": _public_state(state),
                }
                for checkpoint_id, label, state in checkpoints
            ],
            "rival": {
                "trainer_battle_observed": self.saw_trainer_battle,
                "victory_verified": is_rival_victory_verified(
                    self.rival_evidence,
                    saw_trainer_battle=self.saw_trainer_battle,
                ),
                "species": "squirtle",
                "species_id": self.rival_evidence.first_party_species,
                "level": self.rival_evidence.first_party_level,
                "hp": self.rival_evidence.first_party_hp,
                "max_hp": self.rival_evidence.first_party_max_hp,
            },
            "parcel": {
                "received_verified": is_parcel_verified(self.parcel_evidence),
                "delivered_verified": self.pokedex_evidence.oak_got_parcel,
                "present_after_delivery": self.pokedex_evidence.parcel_in_bag,
            },
            "pokedex": {
                "received_verified": is_pokedex_verified(self.pokedex_evidence),
                "controls_ready": self.pokedex_evidence.controls_ready,
            },
            "northbound": pewter["route"],
            "brock": pewter["brock"],
            "cerulean_chapter": self.cerulean.public_dict(),
            "cascade_chapter": self.cascade.public_dict(),
            "facts": sorted(self.facts),
            "objective_progress": {
                "verified": len(self.verified_objectives),
                "total": len(COMPLETION_QUEST),
                "verified_ids": list(self.verified_objectives),
                "next": self.next_objective,
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


class _CountingExecutor:
    def __init__(self, executor: FrameSafeExecutor) -> None:
        self._executor = executor
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> ExecutedAction:
        result = self._executor.execute(action)
        self.actions_executed += 1
        return result


def is_rival_victory_verified(
    state: OaksErrandState,
    *,
    saw_trainer_battle: bool,
) -> bool:
    """Require both a trainer-battle latch and the immutable post-win snapshot."""
    return saw_trainer_battle and state.rival_victory_snapshot


def is_parcel_verified(state: OaksErrandState) -> bool:
    return state.parcel_snapshot


def is_pokedex_verified(state: OaksErrandState) -> bool:
    return state.pokedex_snapshot


def run_qualified_play(
    rom_path: str | Path,
    *,
    watch: bool = False,
    speed: int | None = None,
    new_game_timing: NewGameTiming = DEFAULT_NEW_GAME_TIMING,
    opening_timing: OpeningTiming = DEFAULT_OPENING_TIMING,
    play_timing: QualifiedPlayTiming = DEFAULT_QUALIFIED_PLAY_TIMING,
    progress: ProgressSink | None = None,
    _emulator: PyBoyAdapter | None = None,
) -> QualifiedPlayReport:
    """Run every currently qualified objective in one clean, no-save session."""
    emulator_context = (
        PyBoyAdapter(rom_path, watch=watch, speed=speed)
        if _emulator is None
        else nullcontext(_emulator)
    )
    with emulator_context as emulator:
        opening = run_opening_chapter(
            rom_path,
            new_game_timing=new_game_timing,
            opening_timing=opening_timing,
            progress=_opening_progress_bridge(progress),
            _emulator=emulator,
        )
        reader = PokemonRedStateReader(emulator)
        executor = _CountingExecutor(
            FrameSafeExecutor(emulator, new_game_timing.controller_timing())
        )

        _move(executor, reader, LAB_RIVAL_TRIGGER_DIRECTIONS, "lab rival trigger")
        _expect_position(reader.read(), MapId.OAKS_LAB, 4, 6, "lab rival trigger")
        _wait(executor, play_timing.rival_trigger_wait_frames)
        rival_raw, rival_evidence, saw_trainer_battle = _defeat_lab_rival(
            executor,
            reader,
            play_timing,
        )
        _emit(progress, emulator, "rival_defeated", "Defeated the lab rival", 7)

        _move(executor, reader, LAB_EXIT_DIRECTIONS, "Oak's Lab exit")
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.PALLET_TOWN, 12, 12, "Oak's Lab exit")

        _move(
            executor,
            reader,
            PALLET_TO_ROUTE_1_DIRECTIONS,
            "Pallet Town north route",
        )
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.ROUTE_1, 10, 35, "Route 1 south entrance")

        _wait(executor, play_timing.route_1_north_seed_wait_frames)
        _move(
            executor,
            reader,
            ROUTE_1_TO_VIRIDIAN_DIRECTIONS,
            "Route 1 northbound",
        )
        _wait(executor, play_timing.transition_wait_frames)
        viridian = reader.read()
        _expect_position(viridian, MapId.VIRIDIAN_CITY, 21, 35, "Viridian City entrance")
        _emit(progress, emulator, "viridian_reached", "Reached Viridian City", 8)

        _move(executor, reader, VIRIDIAN_TO_MART_DIRECTIONS, "Viridian Mart route")
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.VIRIDIAN_MART, 3, 7, "Viridian Mart entrance")
        _wait(executor, play_timing.mart_prompt_wait_frames)
        parcel_raw, parcel_evidence = _receive_parcel(
            executor,
            reader,
            play_timing,
        )
        _emit(progress, emulator, "parcel_received", "Received Oak's Parcel", 9)

        _move(executor, reader, MART_EXIT_DIRECTIONS, "Viridian Mart exit")
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.VIRIDIAN_CITY, 29, 20, "Viridian Mart exterior")

        _move(
            executor,
            reader,
            VIRIDIAN_TO_ROUTE_1_DIRECTIONS,
            "Viridian City south route",
        )
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.ROUTE_1, 11, 0, "Route 1 north entrance")

        _wait(executor, play_timing.route_1_south_seed_wait_frames)
        _move(
            executor,
            reader,
            ROUTE_1_TO_PALLET_DIRECTIONS,
            "Route 1 southbound",
        )
        _wait(executor, play_timing.transition_wait_frames)
        pallet_returned = reader.read()
        _expect_position(pallet_returned, MapId.PALLET_TOWN, 10, 0, "Pallet Town return")
        _emit(
            progress,
            emulator,
            "pallet_returned",
            "Returned safely to Pallet Town",
            10,
        )

        _move(executor, reader, PALLET_TO_LAB_DIRECTIONS, "Professor Oak return")
        _wait(executor, play_timing.transition_wait_frames)
        _expect_position(reader.read(), MapId.OAKS_LAB, 5, 11, "Oak's Lab return")
        _move(executor, reader, LAB_TO_OAK_DIRECTIONS, "Professor Oak approach")
        _expect_position(reader.read(), MapId.OAKS_LAB, 5, 3, "Professor Oak")

        executor.execute(MacroAction(MacroActionKind.INTERACT))
        _wait(executor, play_timing.dialogue_wait_frames)
        pokedex_raw, pokedex_evidence = _receive_pokedex(
            executor,
            reader,
            play_timing,
        )
        _emit(
            progress,
            emulator,
            "pokedex_received",
            "Delivered the parcel and received the Pokédex",
            11,
        )

        try:
            pewter = run_pewter_chapter(
                emulator,
                reader,
                executor,
                progress=_pewter_progress_bridge(progress),
            )
        except PewterChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            cerulean = run_cerulean_chapter(
                emulator,
                reader,
                executor,
                progress=_cerulean_progress_bridge(progress),
            )
        except CeruleanChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        try:
            cascade = run_cascade_chapter(
                emulator,
                reader,
                executor,
                progress=_cascade_progress_bridge(progress),
            )
        except CascadeChapterError as error:
            raise QualifiedPlayError(str(error)) from error

        facts = (
            opening.facts
            | semantic_facts(pokedex_raw)
            | semantic_facts(pewter.pewter_reached)
            | semantic_facts(pewter.brock_defeated)
            | semantic_facts(cerulean.cerulean_reached)
            | semantic_facts(cascade.final_raw)
        )
        state = GameState(
            mode=game_mode(cascade.final_raw),
            facts=facts,
            location=location_label(cascade.final_raw.map_id),
        )
        verified_objectives = tuple(
            objective.id
            for objective in COMPLETION_QUEST.topological_order()
            if objective.completion_facts.issubset(facts)
        )
        available = COMPLETION_QUEST.available_objectives(state)
        next_objective = available[0].id if available else None
        report = QualifiedPlayReport(
            rom=emulator.fingerprint,
            pyboy_version=emulator.pyboy_version,
            emulator_window=emulator.window_name,
            emulator_speed=emulator.speed,
            opening=opening,
            rival_defeated=rival_raw,
            viridian_reached=viridian,
            parcel_received=parcel_raw,
            pallet_returned=pallet_returned,
            pokedex_received=pokedex_raw,
            pewter=pewter,
            cerulean=cerulean,
            cascade=cascade,
            rival_evidence=rival_evidence,
            parcel_evidence=parcel_evidence,
            pokedex_evidence=pokedex_evidence,
            saw_trainer_battle=saw_trainer_battle,
            facts=facts,
            verified_objectives=verified_objectives,
            next_objective=next_objective,
            frames_executed=emulator.frame_count,
            actions_executed=opening.actions_executed + executor.actions_executed,
            controller_released=not emulator.pressed_buttons,
        )
        if not report.passed:
            raise QualifiedPlayError("Qualified play evidence failed its public contract.")
        return report


def _defeat_lab_rival(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: QualifiedPlayTiming,
) -> tuple[RawGameState, OaksErrandState, bool]:
    saw_trainer_battle = False
    for pulse in range(timing.max_rival_pulses + 1):
        raw = reader.read()
        state = reader.read_oaks_errand_state(raw)
        if state.phase is OaksErrandPhase.RIVAL_BATTLE:
            saw_trainer_battle = True
        if is_rival_victory_verified(
            state,
            saw_trainer_battle=saw_trainer_battle,
        ):
            return raw, state, saw_trainer_battle
        if pulse == timing.max_rival_pulses:
            break
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        wait_frames = (
            timing.battle_wait_frames
            if raw.battle_state
            else timing.dialogue_wait_frames
        )
        _wait(executor, wait_frames)
    raise QualifiedPlayError("The lab rival failed the bounded verified-victory gate.")


def _receive_parcel(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: QualifiedPlayTiming,
) -> tuple[RawGameState, OaksErrandState]:
    for pulse in range(timing.max_parcel_pulses + 1):
        raw = reader.read()
        state = reader.read_oaks_errand_state(raw)
        if is_parcel_verified(state):
            return raw, state
        if pulse == timing.max_parcel_pulses:
            break
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    raise QualifiedPlayError("Oak's Parcel failed its bounded semantic gate.")


def _receive_pokedex(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: QualifiedPlayTiming,
) -> tuple[RawGameState, OaksErrandState]:
    for pulse in range(timing.max_pokedex_pulses + 1):
        raw = reader.read()
        state = reader.read_oaks_errand_state(raw)
        if is_pokedex_verified(state):
            return raw, state
        if pulse == timing.max_pokedex_pulses:
            break
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    raise QualifiedPlayError("The Pokédex failed its bounded semantic gate.")


def _move(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    label: str,
) -> RawGameState:
    state = reader.read()
    for step, direction in enumerate(directions, start=1):
        if state.battle_state:
            raise QualifiedPlayError(
                f"Unexpected battle interrupted {label} before step {step}."
            )
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        state = reader.read()
        if state.battle_state:
            raise QualifiedPlayError(
                f"Unexpected battle interrupted {label} at step {step}."
            )
    return state


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
        raise QualifiedPlayError(f"The clean run missed the stable {label} gate.")


def _wait(executor: _CountingExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _opening_progress_bridge(sink: ProgressSink | None) -> Callable[[OpeningProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: OpeningProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _pewter_progress_bridge(sink: ProgressSink | None) -> Callable[[PewterProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: PewterProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=POKEDEX_CHECKPOINT_COUNT + progress.completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _cerulean_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[CeruleanProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: CeruleanProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _cascade_progress_bridge(
    sink: ProgressSink | None,
) -> Callable[[CascadeProgress], None] | None:
    if sink is None:
        return None

    def emit(progress: CascadeProgress) -> None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=progress.checkpoint_id,
                label=progress.label,
                completed=(
                    POKEDEX_CHECKPOINT_COUNT
                    + PEWTER_CHECKPOINT_COUNT
                    + CERULEAN_CHECKPOINT_COUNT
                    + progress.completed
                ),
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=progress.frames_executed,
            )
        )

    return emit


def _emit(
    sink: ProgressSink | None,
    emulator: PyBoyAdapter,
    checkpoint_id: str,
    label: str,
    completed: int,
) -> None:
    if sink is not None:
        sink(
            QualifiedPlayProgress(
                checkpoint_id=checkpoint_id,
                label=label,
                completed=completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=emulator.frame_count,
            )
        )


def _public_state(state: RawGameState) -> dict[str, object]:
    return {
        "mode": game_mode(state).value,
        "map_id": state.map_id,
        "location": location_label(state.map_id),
        "player_x": state.player_x,
        "player_y": state.player_y,
        "party_count": state.party_count,
        "battle_state": state.battle_state,
    }


assert (
    OPENING_CHECKPOINT_COUNT
    < POKEDEX_CHECKPOINT_COUNT
    < POKEDEX_CHECKPOINT_COUNT + PEWTER_CHECKPOINT_COUNT
    < POKEDEX_CHECKPOINT_COUNT + PEWTER_CHECKPOINT_COUNT + CERULEAN_CHECKPOINT_COUNT
    < QUALIFIED_PLAY_CHECKPOINT_COUNT
)
