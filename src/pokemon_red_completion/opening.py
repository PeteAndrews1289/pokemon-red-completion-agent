"""Bounded clean-start teacher for the opening through a verified starter.

The qualified corridors and semantic gates are derived from pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8`` and independently verified on
the supported ROM. The concluded predecessor contributes only the already
attributed clean-power-on bootstrap; it did not publish this route.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.bootstrap import (
    DEFAULT_NEW_GAME_TIMING,
    NewGameTiming,
    is_bedroom_input_ready,
    is_clean_bedroom_start,
    play_new_game_intro,
)
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import ExecutedAction, FrameSafeExecutor
from pokemon_red_completion.navigation import Coordinate, path_to_directions
from pokemon_red_completion.observation import (
    SQUIRTLE_SPECIES_ID,
    MapId,
    OpeningControlState,
    OpeningPhase,
    PokemonRedStateReader,
    RawGameState,
    SemanticStateTracker,
    game_mode,
    location_label,
)
from pokemon_red_completion.rom import RomFingerprint
from pokemon_red_completion.route import COMPLETION_QUEST

PRET_POKERED_COMMIT = "1e96034092686d006e863cace09e87273051a3d8"
OPENING_CHECKPOINT_COUNT = 6
SQUIRTLE_LABEL = "squirtle"

BEDROOM_CORRIDOR = (
    Coordinate(3, 6),
    Coordinate(4, 6),
    Coordinate(5, 6),
    Coordinate(5, 5),
    Coordinate(5, 4),
    Coordinate(5, 3),
    Coordinate(5, 2),
    Coordinate(5, 1),
    Coordinate(6, 1),
    Coordinate(7, 1),
)
HOUSE_1F_CORRIDOR = (
    Coordinate(7, 1),
    Coordinate(6, 1),
    Coordinate(6, 2),
    Coordinate(6, 3),
    Coordinate(6, 4),
    Coordinate(6, 5),
    Coordinate(6, 6),
    Coordinate(6, 7),
    Coordinate(5, 7),
    Coordinate(4, 7),
    Coordinate(3, 7),
)
PALLET_CORRIDOR = (
    Coordinate(5, 6),
    Coordinate(6, 6),
    Coordinate(7, 6),
    Coordinate(8, 6),
    Coordinate(8, 5),
    Coordinate(8, 4),
    Coordinate(8, 3),
    Coordinate(8, 2),
    Coordinate(9, 2),
    Coordinate(10, 2),
    Coordinate(10, 1),
)
SQUIRTLE_APPROACH = (
    Coordinate(5, 3),
    Coordinate(5, 4),
    Coordinate(6, 4),
    Coordinate(7, 4),
)


class OpeningChapterError(RuntimeError):
    """Raised when the bounded opening teacher misses a semantic gate."""


@dataclass(frozen=True, slots=True)
class OpeningTiming:
    transition_wait_frames: int = 120
    oak_trigger_wait_frames: int = 360
    dialogue_wait_frames: int = 240
    starter_text_wait_frames: int = 180
    max_escort_pulses: int = 32
    max_starter_confirm_pulses: int = 12
    max_starter_cancel_pulses: int = 12

    def __post_init__(self) -> None:
        for name, value in (
            ("transition_wait_frames", self.transition_wait_frames),
            ("oak_trigger_wait_frames", self.oak_trigger_wait_frames),
            ("dialogue_wait_frames", self.dialogue_wait_frames),
            ("starter_text_wait_frames", self.starter_text_wait_frames),
            ("max_escort_pulses", self.max_escort_pulses),
            ("max_starter_confirm_pulses", self.max_starter_confirm_pulses),
            ("max_starter_cancel_pulses", self.max_starter_cancel_pulses),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_OPENING_TIMING = OpeningTiming()


@dataclass(frozen=True, slots=True)
class OpeningProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[OpeningProgress], None]


@dataclass(frozen=True, slots=True)
class OpeningChapterReport:
    rom: RomFingerprint
    pyboy_version: str
    emulator_window: str
    emulator_speed: int
    clean_power_on: bool
    bedroom: RawGameState
    downstairs: RawGameState
    outside: RawGameState
    oak_triggered: RawGameState
    selection_ready: RawGameState
    starter: RawGameState
    selection_control: OpeningControlState
    starter_control: OpeningControlState
    facts: frozenset[str]
    verified_objectives: tuple[str, ...]
    next_objective: str | None
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            self.clean_power_on
            and is_clean_bedroom_start(self.bedroom)
            and self.downstairs.map_id == MapId.REDS_HOUSE_1F
            and self.outside.map_id == MapId.PALLET_TOWN
            and self.selection_control.phase is OpeningPhase.STARTER_SELECTION_READY
            and self.starter_control.phase is OpeningPhase.STARTER_OBTAINED
            and self.starter_control.first_party_species == SQUIRTLE_SPECIES_ID
            and "party:starter_obtained" in self.facts
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        checkpoints = (
            ("bedroom_ready", "Bedroom input ready", self.bedroom),
            ("downstairs", "Reached Red's house first floor", self.downstairs),
            ("outside", "Exited into Pallet Town", self.outside),
            ("oak_triggered", "Triggered Professor Oak", self.oak_triggered),
            ("selection_ready", "Reached the starter selection gate", self.selection_ready),
            ("starter_obtained", "Selected and verified Squirtle", self.starter),
        )
        return {
            "schema": "opening-chapter-v1",
            "status": "ok" if self.passed else "failed",
            "rom": self.rom.public_dict(),
            "emulator": {
                "name": "PyBoy",
                "version": self.pyboy_version,
                "window": self.emulator_window,
                "speed": self.emulator_speed,
                "human_input": False,
                "save_on_exit": False,
            },
            "clean_power_on": self.clean_power_on,
            "checkpoints": [
                {
                    "id": checkpoint_id,
                    "label": label,
                    "status": "verified",
                    "state": _public_state(state),
                }
                for checkpoint_id, label, state in checkpoints
            ],
            "starter": {
                "species": SQUIRTLE_LABEL,
                "species_id": SQUIRTLE_SPECIES_ID,
                "party_count": self.starter.party_count,
                "event_verified": self.starter_control.starter_obtained,
                "controls_ready": self.starter_control.all_controls_allowed,
            },
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


class OpeningExecutor(Protocol):
    def execute(self, action: MacroAction) -> ExecutedAction: ...


class _CountingExecutor:
    def __init__(self, executor: OpeningExecutor) -> None:
        self._executor = executor
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> ExecutedAction:
        result = self._executor.execute(action)
        self.actions_executed += 1
        return result


def run_opening_chapter(
    rom_path: str | Path,
    *,
    watch: bool = False,
    speed: int | None = None,
    new_game_timing: NewGameTiming = DEFAULT_NEW_GAME_TIMING,
    opening_timing: OpeningTiming = DEFAULT_OPENING_TIMING,
    progress: ProgressSink | None = None,
    _emulator: PyBoyAdapter | None = None,
    _executor: OpeningExecutor | None = None,
) -> OpeningChapterReport:
    emulator_context = (
        PyBoyAdapter(rom_path, watch=watch, speed=speed)
        if _emulator is None
        else nullcontext(_emulator)
    )
    with emulator_context as emulator:
        reader = PokemonRedStateReader(emulator)
        initial = reader.read()
        tracker = SemanticStateTracker(initial)
        executor = _CountingExecutor(
            _executor or FrameSafeExecutor(emulator, new_game_timing.controller_timing())
        )

        play_new_game_intro(executor, timing=new_game_timing)
        bedroom = reader.read()
        bedroom_input = reader.read_bedroom_input_state()
        bedroom_control = reader.read_opening_control_state(bedroom)
        if (
            not is_bedroom_input_ready(bedroom, bedroom_input)
            or bedroom_control.phase is not OpeningPhase.BEDROOM_READY
        ):
            raise OpeningChapterError("The clean run missed the input-ready bedroom gate.")
        _emit(progress, emulator, "bedroom_ready", "Bedroom input ready", 1)

        downstairs = _follow_corridor(
            executor,
            reader,
            MapId.REDS_HOUSE_2F,
            BEDROOM_CORRIDOR,
            final_map=MapId.REDS_HOUSE_1F,
        )
        _wait(executor, opening_timing.transition_wait_frames)
        downstairs = reader.read()
        if (
            downstairs.map_id != MapId.REDS_HOUSE_1F
            or downstairs.player_x != 7
            or downstairs.player_y != 1
            or reader.read_opening_control_state(downstairs).phase is not OpeningPhase.DOWNSTAIRS
        ):
            raise OpeningChapterError("The clean run missed Red's house first-floor gate.")
        _emit(progress, emulator, "downstairs", "Reached Red's house first floor", 2)

        _follow_corridor(
            executor,
            reader,
            MapId.REDS_HOUSE_1F,
            HOUSE_1F_CORRIDOR,
        )
        executor.execute(MacroAction(MacroActionKind.MOVE, "down"))
        if reader.read().map_id != MapId.PALLET_TOWN:
            raise OpeningChapterError("The clean run failed the front-door transition.")
        _wait(executor, opening_timing.transition_wait_frames)
        outside = reader.read()
        if (
            outside.map_id != MapId.PALLET_TOWN
            or outside.player_x != 5
            or outside.player_y != 6
            or reader.read_opening_control_state(outside).phase is not OpeningPhase.PALLET_FREE
        ):
            raise OpeningChapterError("The clean run missed the stable Pallet Town gate.")
        _emit(progress, emulator, "outside", "Exited into Pallet Town", 3)

        oak_triggered = _follow_corridor(
            executor,
            reader,
            MapId.PALLET_TOWN,
            PALLET_CORRIDOR,
        )
        oak_control = reader.read_opening_control_state(oak_triggered)
        if oak_control.phase is not OpeningPhase.OAK_ESCORT:
            raise OpeningChapterError("The clean run failed to trigger Professor Oak.")
        _emit(progress, emulator, "oak_triggered", "Triggered Professor Oak", 4)

        _wait(executor, opening_timing.oak_trigger_wait_frames)
        selection_ready, selection_control = _advance_until_phase(
            executor,
            reader,
            OpeningPhase.STARTER_SELECTION_READY,
            opening_timing.max_escort_pulses,
            opening_timing.dialogue_wait_frames,
            prefer_cancel=False,
        )
        _emit(
            progress,
            emulator,
            "selection_ready",
            "Reached the starter selection gate",
            5,
        )

        _follow_corridor(
            executor,
            reader,
            MapId.OAKS_LAB,
            SQUIRTLE_APPROACH,
        )
        executor.execute(MacroAction(MacroActionKind.MOVE, "up"))
        faced_ball = reader.read()
        if (
            faced_ball.map_id != MapId.OAKS_LAB
            or faced_ball.player_x != 7
            or faced_ball.player_y != 4
        ):
            raise OpeningChapterError("The teacher failed to face Squirtle's Poké Ball.")
        executor.execute(MacroAction(MacroActionKind.INTERACT))
        _wait(executor, opening_timing.dialogue_wait_frames)

        _advance_until_party(
            executor,
            reader,
            opening_timing.max_starter_confirm_pulses,
            opening_timing.starter_text_wait_frames,
        )
        starter, starter_control = _advance_until_phase(
            executor,
            reader,
            OpeningPhase.STARTER_OBTAINED,
            opening_timing.max_starter_cancel_pulses,
            opening_timing.dialogue_wait_frames,
            prefer_cancel=True,
        )
        if starter_control.first_party_species != SQUIRTLE_SPECIES_ID:
            raise OpeningChapterError("The verified starter is not Squirtle.")
        state = tracker.observe(starter)
        _emit(progress, emulator, "starter_obtained", "Selected and verified Squirtle", 6)

        verified_objectives = tuple(
            objective.id
            for objective in COMPLETION_QUEST.topological_order()
            if objective.completion_facts.issubset(state.facts)
        )
        available = COMPLETION_QUEST.available_objectives(state)
        next_objective = available[0].id if available else None
        report = OpeningChapterReport(
            rom=emulator.fingerprint,
            pyboy_version=emulator.pyboy_version,
            emulator_window=emulator.window_name,
            emulator_speed=emulator.speed,
            clean_power_on="system:clean_power_on" in state.facts,
            bedroom=bedroom,
            downstairs=downstairs,
            outside=outside,
            oak_triggered=oak_triggered,
            selection_ready=selection_ready,
            starter=starter,
            selection_control=selection_control,
            starter_control=starter_control,
            facts=state.facts,
            verified_objectives=verified_objectives,
            next_objective=next_objective,
            frames_executed=emulator.frame_count,
            actions_executed=executor.actions_executed,
            controller_released=not emulator.pressed_buttons,
        )
        if not report.passed:
            raise OpeningChapterError("Opening chapter evidence failed its public contract.")
        return report


def _follow_corridor(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    map_id: MapId,
    path: tuple[Coordinate, ...],
    *,
    final_map: MapId | None = None,
) -> RawGameState:
    state = reader.read()
    if state.map_id != map_id or state.player_x != path[0].x or state.player_y != path[0].y:
        raise OpeningChapterError(
            f"Qualified corridor has unexpected origin for {map_id.name.lower()}."
        )

    directions = path_to_directions(path)
    for index, direction in enumerate(directions, start=1):
        executor.execute(MacroAction(MacroActionKind.MOVE, direction.value))
        state = reader.read()
        expected_map = final_map if final_map is not None and index == len(directions) else map_id
        expected = path[index]
        if (
            state.map_id != expected_map
            or state.player_x != expected.x
            or state.player_y != expected.y
        ):
            raise OpeningChapterError(
                f"Qualified corridor diverged at step {index} in {map_id.name.lower()}."
            )
    return state


def _advance_until_phase(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    target: OpeningPhase,
    max_pulses: int,
    wait_frames: int,
    *,
    prefer_cancel: bool,
) -> tuple[RawGameState, OpeningControlState]:
    for pulse in range(max_pulses + 1):
        raw = reader.read()
        control = reader.read_opening_control_state(raw)
        if control.phase is target:
            return raw, control
        if pulse == max_pulses:
            break
        if prefer_cancel and control.cancel_allowed:
            executor.execute(MacroAction(MacroActionKind.CANCEL))
        elif not prefer_cancel and control.confirm_allowed:
            executor.execute(MacroAction(MacroActionKind.CONFIRM))
        else:
            _wait(executor, 24)
        _wait(executor, wait_frames)
    raise OpeningChapterError(f"Opening dialogue failed to reach {target.value}.")


def _advance_until_party(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    max_pulses: int,
    wait_frames: int,
) -> RawGameState:
    for pulse in range(max_pulses + 1):
        raw = reader.read()
        control = reader.read_opening_control_state(raw)
        if raw.party_count:
            if control.first_party_species != SQUIRTLE_SPECIES_ID:
                raise OpeningChapterError("Starter selection produced an unexpected species.")
            return raw
        if pulse == max_pulses:
            break
        if control.confirm_allowed:
            executor.execute(MacroAction(MacroActionKind.CONFIRM))
        else:
            _wait(executor, 24)
        _wait(executor, wait_frames)
    raise OpeningChapterError("Starter selection failed to populate the party.")


def _wait(executor: _CountingExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _emit(
    sink: ProgressSink | None,
    emulator: PyBoyAdapter,
    checkpoint_id: str,
    label: str,
    completed: int,
) -> None:
    if sink is not None:
        sink(
            OpeningProgress(
                checkpoint_id=checkpoint_id,
                label=label,
                completed=completed,
                total=OPENING_CHECKPOINT_COUNT,
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
