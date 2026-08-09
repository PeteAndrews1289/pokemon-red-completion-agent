from __future__ import annotations

import hashlib
import json
import os
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from pokemon_red_completion import opening
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.navigation import Coordinate, Direction, path_to_directions
from pokemon_red_completion.observation import (
    EVENT_FLAG_BYTES,
    SQUIRTLE_SPECIES_ID,
    BedroomInputState,
    MapId,
    OpeningControlState,
    OpeningPhase,
    RawGameState,
)
from pokemon_red_completion.opening import (
    BEDROOM_CORRIDOR,
    DEFAULT_OPENING_TIMING,
    HOUSE_1F_CORRIDOR,
    OPENING_CHECKPOINT_COUNT,
    PALLET_CORRIDOR,
    SQUIRTLE_APPROACH,
    OpeningChapterError,
    OpeningChapterReport,
    OpeningTiming,
    _advance_to_bedroom_ready,
)
from pokemon_red_completion.rom import RomFingerprint


def _raw(
    map_id: MapId,
    x: int,
    y: int,
    *,
    party_count: int = 0,
    party_species_ids: tuple[int, ...] = (),
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=int(map_id),
        player_x=x,
        player_y=y,
        party_count=party_count,
        battle_state=0,
        badge_bits=0,
        bag_item_ids=(),
        event_flags=bytes(EVENT_FLAG_BYTES),
        party_species_ids=party_species_ids,
    )


def _control(
    phase: OpeningPhase,
    *,
    confirm_allowed: bool = True,
    cancel_allowed: bool = True,
    movement_allowed: bool = True,
    followed_oak_into_lab: bool = False,
    asked_to_choose: bool = False,
    starter_obtained: bool = False,
    first_party_species: int | None = None,
) -> OpeningControlState:
    return OpeningControlState(
        phase=phase,
        confirm_allowed=confirm_allowed,
        cancel_allowed=cancel_allowed,
        movement_allowed=movement_allowed,
        followed_oak_into_lab=followed_oak_into_lab,
        asked_to_choose=asked_to_choose,
        starter_obtained=starter_obtained,
        first_party_species=first_party_species,
    )


def test_qualified_opening_corridors_are_exact_and_cardinal() -> None:
    assert (
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
    ) == BEDROOM_CORRIDOR
    assert (
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
    ) == HOUSE_1F_CORRIDOR
    assert (
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
    ) == PALLET_CORRIDOR
    assert (
        Coordinate(5, 3),
        Coordinate(5, 4),
        Coordinate(6, 4),
        Coordinate(7, 4),
    ) == SQUIRTLE_APPROACH

    assert tuple(path_to_directions(BEDROOM_CORRIDOR)) == (
        *([Direction.RIGHT] * 2),
        *([Direction.UP] * 5),
        *([Direction.RIGHT] * 2),
    )
    assert tuple(path_to_directions(HOUSE_1F_CORRIDOR)) == (
        Direction.LEFT,
        *([Direction.DOWN] * 6),
        *([Direction.LEFT] * 3),
    )
    assert tuple(path_to_directions(PALLET_CORRIDOR)) == (
        *([Direction.RIGHT] * 3),
        *([Direction.UP] * 4),
        *([Direction.RIGHT] * 2),
        Direction.UP,
    )
    assert tuple(path_to_directions(SQUIRTLE_APPROACH)) == (
        Direction.DOWN,
        Direction.RIGHT,
        Direction.RIGHT,
    )


@pytest.mark.parametrize(
    "field_name",
    (
        "transition_wait_frames",
        "oak_trigger_wait_frames",
        "dialogue_wait_frames",
        "starter_text_wait_frames",
        "max_escort_pulses",
        "max_starter_confirm_pulses",
        "max_starter_cancel_pulses",
        "max_bedroom_recovery_pulses",
        "bedroom_recovery_wait_frames",
    ),
)
@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_opening_timing_rejects_unbounded_values(
    field_name: str,
    invalid: object,
) -> None:
    with pytest.raises(ValueError, match=f"{field_name} must be a positive integer"):
        replace(DEFAULT_OPENING_TIMING, **{field_name: invalid})


def test_opening_timing_defaults_are_source_stable() -> None:
    assert OpeningTiming() == OpeningTiming(
        transition_wait_frames=120,
        oak_trigger_wait_frames=360,
        dialogue_wait_frames=240,
        starter_text_wait_frames=180,
        max_escort_pulses=32,
        max_starter_confirm_pulses=12,
        max_starter_cancel_pulses=12,
        max_bedroom_recovery_pulses=32,
        bedroom_recovery_wait_frames=240,
    )


def test_bedroom_gate_recovers_a_timing_shifted_frontend_with_bounded_pulses() -> None:
    frontend = replace(
        _raw(MapId.REDS_HOUSE_2F, 3, 6),
        game_started=False,
        map_id=None,
        player_x=None,
        player_y=None,
        party_count=None,
        battle_state=None,
    )
    bedroom = _raw(MapId.REDS_HOUSE_2F, 3, 6)

    class _Reader:
        state = frontend

        def read(self) -> RawGameState:
            return self.state

        def read_bedroom_input_state(self) -> BedroomInputState:
            return BedroomInputState(joy_ignore=0, map_script=1)

        def read_opening_control_state(self, raw: RawGameState) -> OpeningControlState:
            return _control(OpeningPhase.BEDROOM_READY if raw is bedroom else OpeningPhase.UNKNOWN)

    reader = _Reader()

    class _Executor:
        actions: list[MacroAction] = []
        frontend_pulses = 0

        def execute(self, action: MacroAction) -> object:
            self.actions.append(action)
            if action.kind is not MacroActionKind.WAIT:
                self.frontend_pulses += 1
                if self.frontend_pulses == 2:
                    reader.state = bedroom
            return object()

    executor = _Executor()
    observed, pulses = _advance_to_bedroom_ready(  # type: ignore[arg-type]
        executor,
        reader,  # type: ignore[arg-type]
        DEFAULT_OPENING_TIMING,
    )

    assert observed is bedroom
    assert pulses == 2
    assert [action.kind for action in executor.actions] == [
        MacroActionKind.OPEN_MENU,
        MacroActionKind.WAIT,
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
    ]


def test_bedroom_gate_rejects_an_unexpected_started_map_without_input() -> None:
    wrong_map = _raw(MapId.PALLET_TOWN, 5, 6)

    class _Reader:
        def read(self) -> RawGameState:
            return wrong_map

        def read_bedroom_input_state(self) -> BedroomInputState:
            return BedroomInputState(joy_ignore=0, map_script=0)

        def read_opening_control_state(self, _raw: RawGameState) -> OpeningControlState:
            return _control(OpeningPhase.PALLET_FREE)

    class _Executor:
        def execute(self, _action: MacroAction) -> object:
            raise AssertionError("unexpected input")

    with pytest.raises(OpeningChapterError, match="unexpected in-game boundary"):
        _advance_to_bedroom_ready(  # type: ignore[arg-type]
            _Executor(),
            _Reader(),  # type: ignore[arg-type]
            DEFAULT_OPENING_TIMING,
        )


def test_bedroom_gate_fails_after_the_declared_frontend_input_bound() -> None:
    frontend = replace(
        _raw(MapId.REDS_HOUSE_2F, 3, 6),
        game_started=False,
        map_id=None,
        player_x=None,
        player_y=None,
        party_count=None,
        battle_state=None,
    )

    class _Reader:
        def read(self) -> RawGameState:
            return frontend

        def read_bedroom_input_state(self) -> BedroomInputState:
            return BedroomInputState(joy_ignore=0, map_script=0)

        def read_opening_control_state(self, _raw: RawGameState) -> OpeningControlState:
            return _control(OpeningPhase.UNKNOWN)

    class _Executor:
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> object:
            self.actions.append(action)
            return object()

    executor = _Executor()
    timing = replace(DEFAULT_OPENING_TIMING, max_bedroom_recovery_pulses=3)
    with pytest.raises(OpeningChapterError, match="bounded input-ready bedroom gate"):
        _advance_to_bedroom_ready(  # type: ignore[arg-type]
            executor,
            _Reader(),  # type: ignore[arg-type]
            timing,
        )

    assert [action.kind for action in executor.actions] == [
        MacroActionKind.OPEN_MENU,
        MacroActionKind.WAIT,
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
    ]


def test_bedroom_gate_settles_clean_bedroom_without_counting_an_input() -> None:
    bedroom = _raw(MapId.REDS_HOUSE_2F, 3, 6)

    class _Reader:
        ready = False

        def read(self) -> RawGameState:
            return bedroom

        def read_bedroom_input_state(self) -> BedroomInputState:
            return BedroomInputState(joy_ignore=0, map_script=1 if self.ready else 0)

        def read_opening_control_state(self, _raw: RawGameState) -> OpeningControlState:
            return _control(OpeningPhase.BEDROOM_READY)

    reader = _Reader()

    class _Executor:
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> object:
            self.actions.append(action)
            if action.kind is MacroActionKind.WAIT:
                reader.ready = True
            return object()

    executor = _Executor()
    observed, pulses = _advance_to_bedroom_ready(  # type: ignore[arg-type]
        executor,
        reader,  # type: ignore[arg-type]
        DEFAULT_OPENING_TIMING,
    )

    assert observed is bedroom
    assert pulses == 0
    assert [action.kind for action in executor.actions] == [MacroActionKind.WAIT]


def test_public_opening_report_is_complete_and_privacy_safe() -> None:
    bedroom = _raw(MapId.REDS_HOUSE_2F, 3, 6)
    downstairs = _raw(MapId.REDS_HOUSE_1F, 7, 1)
    outside = _raw(MapId.PALLET_TOWN, 5, 6)
    oak_triggered = _raw(MapId.PALLET_TOWN, 10, 1)
    selection_ready = _raw(MapId.OAKS_LAB, 5, 3)
    starter = _raw(
        MapId.OAKS_LAB,
        7,
        4,
        party_count=1,
        party_species_ids=(SQUIRTLE_SPECIES_ID,),
    )
    report = OpeningChapterReport(
        rom=RomFingerprint(
            filename="/private/home/Pokemon Red.gb",
            title="POKEMON RED",
            size_bytes=1_048_576,
            sha1="1" * 40,
            sha256="2" * 64,
        ),
        pyboy_version="2.7.0",
        emulator_window="SDL2",
        emulator_speed=2,
        clean_power_on=True,
        bedroom_recovery_pulses=0,
        bedroom=bedroom,
        downstairs=downstairs,
        outside=outside,
        oak_triggered=oak_triggered,
        selection_ready=selection_ready,
        starter=starter,
        selection_control=_control(
            OpeningPhase.STARTER_SELECTION_READY,
            followed_oak_into_lab=True,
            asked_to_choose=True,
        ),
        starter_control=_control(
            OpeningPhase.STARTER_OBTAINED,
            starter_obtained=True,
            first_party_species=SQUIRTLE_SPECIES_ID,
        ),
        facts=frozenset(
            {
                "system:clean_power_on",
                "story:adventure_begun",
                "party:starter_obtained",
            }
        ),
        verified_objectives=("power_on", "begin_adventure", "choose_starter"),
        next_objective="receive_pokedex",
        frames_executed=20_000,
        actions_executed=100,
        controller_released=True,
    )

    public = report.public_dict()
    serialized = json.dumps(public, sort_keys=True)

    assert report.passed
    assert public["schema"] == "opening-chapter-v1"
    assert public["status"] == "ok"
    assert public["bedroom_recovery_pulses"] == 0
    assert [checkpoint["id"] for checkpoint in public["checkpoints"]] == [
        "bedroom_ready",
        "downstairs",
        "outside",
        "oak_triggered",
        "selection_ready",
        "starter_obtained",
    ]
    assert public["starter"] == {
        "species": "squirtle",
        "species_id": SQUIRTLE_SPECIES_ID,
        "party_count": 1,
        "event_verified": True,
        "controls_ready": True,
    }
    assert public["objective_progress"]["verified_ids"] == [
        "power_on",
        "begin_adventure",
        "choose_starter",
    ]
    assert public["objective_progress"]["next"] == "receive_pokedex"
    assert "/private" not in serialized
    assert "Pokemon Red.gb" not in serialized
    assert "filename" not in serialized
    assert "event_flags" not in serialized
    assert "party_species_ids" not in serialized


class RecordingExecutor:
    def __init__(self) -> None:
        self.actions: list[MacroAction] = []

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)


class ConstantReader:
    def __init__(self, raw: RawGameState, control: OpeningControlState) -> None:
        self.raw = raw
        self.control = control

    def read(self) -> RawGameState:
        return self.raw

    def read_opening_control_state(self, raw: RawGameState) -> OpeningControlState:
        assert raw is self.raw
        return self.control


def test_phase_helper_obeys_exact_pulse_budget() -> None:
    executor = RecordingExecutor()
    reader = ConstantReader(
        _raw(MapId.PALLET_TOWN, 10, 1),
        _control(OpeningPhase.OAK_ESCORT, movement_allowed=False),
    )

    with pytest.raises(OpeningChapterError, match="starter_selection_ready"):
        opening._advance_until_phase(
            executor,
            reader,
            OpeningPhase.STARTER_SELECTION_READY,
            max_pulses=2,
            wait_frames=7,
            prefer_cancel=False,
        )

    assert [action.kind for action in executor.actions] == [
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
    ]
    wait_repeats = [
        action.repeat for action in executor.actions if action.kind is MacroActionKind.WAIT
    ]
    assert wait_repeats == [
        7,
        7,
    ]


def test_party_helper_obeys_exact_pulse_budget() -> None:
    executor = RecordingExecutor()
    reader = ConstantReader(
        _raw(MapId.OAKS_LAB, 7, 4),
        _control(OpeningPhase.STARTER_SELECTION_READY),
    )

    with pytest.raises(OpeningChapterError, match="populate the party"):
        opening._advance_until_party(
            executor,
            reader,
            max_pulses=2,
            wait_frames=9,
        )

    assert [action.kind for action in executor.actions] == [
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
    ]


def test_party_helper_rejects_wrong_species_without_more_input() -> None:
    executor = RecordingExecutor()
    raw = _raw(
        MapId.OAKS_LAB,
        7,
        4,
        party_count=1,
        party_species_ids=(0xB0,),
    )
    reader = ConstantReader(
        raw,
        _control(
            OpeningPhase.STARTER_OBTAINED,
            first_party_species=0xB0,
        ),
    )

    with pytest.raises(OpeningChapterError, match="unexpected species"):
        opening._advance_until_party(executor, reader, max_pulses=2, wait_frames=9)

    assert executor.actions == []


def test_progress_emission_is_sanitized_and_immutable() -> None:
    class FakeEmulator:
        frame_count = 12_345

    progress: list[opening.OpeningProgress] = []

    opening._emit(
        progress.append,
        FakeEmulator(),
        "selection_ready",
        "Reached the starter selection gate",
        5,
    )

    assert progress == [
        opening.OpeningProgress(
            checkpoint_id="selection_ready",
            label="Reached the starter selection gate",
            completed=5,
            total=OPENING_CHECKPOINT_COUNT,
            frames_executed=12_345,
        )
    ]
    with pytest.raises(FrozenInstanceError):
        progress[0].completed = 6  # type: ignore[misc]


def _adjacent_artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.integration
def test_private_rom_reaches_verified_squirtle_without_adjacent_artifacts() -> None:
    raw_path = os.environ.get("POKEMON_RED_ROM")
    if not raw_path:
        pytest.skip("Set POKEMON_RED_ROM to run the private integration test")

    rom_path = Path(raw_path).expanduser().resolve()
    adjacent = tuple(Path(f"{rom_path}{suffix}") for suffix in (".ram", ".rtc", ".state"))
    before = tuple(_adjacent_artifact_identity(path) for path in adjacent)

    report = opening.run_opening_chapter(rom_path)

    after = tuple(_adjacent_artifact_identity(path) for path in adjacent)
    assert report.passed
    assert report.starter.map_id == MapId.OAKS_LAB
    assert (report.starter.player_x, report.starter.player_y) == (7, 4)
    assert report.starter.party_species_ids == (SQUIRTLE_SPECIES_ID,)
    assert report.starter_control.phase is OpeningPhase.STARTER_OBTAINED
    assert report.starter_control.starter_obtained
    assert report.starter_control.all_controls_allowed
    assert report.verified_objectives == (
        "power_on",
        "begin_adventure",
        "choose_starter",
    )
    assert report.next_objective == "receive_pokedex"
    assert report.frames_executed == 21_216
    assert before == after
