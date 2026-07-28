from __future__ import annotations

import hashlib
import json
import os
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from pokemon_red_completion.observation import (
    SQUIRTLE_SPECIES_ID,
    MapId,
    OaksErrandPhase,
    OaksErrandState,
    OpeningControlState,
    OpeningPhase,
    RawGameState,
)
from pokemon_red_completion.opening import OpeningChapterReport
from pokemon_red_completion.play import (
    DEFAULT_QUALIFIED_PLAY_TIMING,
    LAB_EXIT_DIRECTIONS,
    LAB_RIVAL_TRIGGER_DIRECTIONS,
    PALLET_TO_ROUTE_1_DIRECTIONS,
    QUALIFIED_PLAY_CHECKPOINT_COUNT,
    ROUTE_1_TO_VIRIDIAN_DIRECTIONS,
    VIRIDIAN_TO_MART_DIRECTIONS,
    QualifiedPlayProgress,
    QualifiedPlayReport,
    QualifiedPlayTiming,
    is_parcel_verified,
    is_pokedex_verified,
    is_rival_victory_verified,
    run_qualified_play,
)
from pokemon_red_completion.rom import RomFingerprint


def _raw(
    map_id: MapId,
    x: int,
    y: int,
    *,
    party_count: int = 1,
    party_species_ids: tuple[int, ...] = (SQUIRTLE_SPECIES_ID,),
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
        event_flags=b"",
        party_species_ids=party_species_ids,
        first_party_level=6 if party_count else None,
        first_party_hp=21 if party_count else None,
        first_party_max_hp=21 if party_count else None,
        battle_result=0,
    )


def _opening_control(
    phase: OpeningPhase,
    *,
    starter_obtained: bool = False,
    first_party_species: int | None = None,
) -> OpeningControlState:
    return OpeningControlState(
        phase=phase,
        confirm_allowed=True,
        cancel_allowed=True,
        movement_allowed=True,
        followed_oak_into_lab=True,
        asked_to_choose=True,
        starter_obtained=starter_obtained,
        first_party_species=first_party_species,
    )


def _rival_victory() -> OaksErrandState:
    return OaksErrandState(
        phase=OaksErrandPhase.RIVAL_DEFEATED,
        joy_ignore=0,
        lab_script=18,
        mart_script=0,
        battled_rival=True,
        got_oaks_parcel=False,
        oak_got_parcel=False,
        got_pokedex=False,
        parcel_in_bag=False,
        first_party_species=SQUIRTLE_SPECIES_ID,
        first_party_level=6,
        first_party_hp=21,
        first_party_max_hp=21,
        battle_result=0,
        map_id=MapId.OAKS_LAB,
        battle_state=0,
    )


def _parcel_obtained() -> OaksErrandState:
    return OaksErrandState(
        phase=OaksErrandPhase.PARCEL_OBTAINED,
        joy_ignore=0,
        lab_script=0,
        mart_script=2,
        battled_rival=True,
        got_oaks_parcel=True,
        oak_got_parcel=False,
        got_pokedex=False,
        parcel_in_bag=True,
        first_party_species=SQUIRTLE_SPECIES_ID,
        first_party_level=6,
        first_party_hp=21,
        first_party_max_hp=21,
        battle_result=0,
        map_id=MapId.VIRIDIAN_MART,
        battle_state=0,
    )


def _pokedex_obtained() -> OaksErrandState:
    return OaksErrandState(
        phase=OaksErrandPhase.POKEDEX_OBTAINED,
        joy_ignore=0,
        lab_script=18,
        mart_script=2,
        battled_rival=True,
        got_oaks_parcel=True,
        oak_got_parcel=True,
        got_pokedex=True,
        parcel_in_bag=False,
        first_party_species=SQUIRTLE_SPECIES_ID,
        first_party_level=6,
        first_party_hp=21,
        first_party_max_hp=21,
        # A successful Route 1 escape legitimately overwrites the earlier
        # rival-battle result. The final gate must rely on the captured rival
        # checkpoint rather than reinterpret this byte.
        battle_result=2,
        map_id=MapId.OAKS_LAB,
        battle_state=0,
    )


def test_qualified_play_direction_sequences_are_source_stable() -> None:
    assert LAB_RIVAL_TRIGGER_DIRECTIONS == (
        "down",
        "left",
        "left",
        "left",
        "down",
    )
    assert LAB_EXIT_DIRECTIONS == ("down",) * 6
    assert (
        *(("left",) * 3),
        *(("up",) * 10),
        "right",
        *(("up",) * 3),
    ) == PALLET_TO_ROUTE_1_DIRECTIONS
    assert (
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
    ) == ROUTE_1_TO_VIRIDIAN_DIRECTIONS
    assert (
        *(("up",) * 5),
        "left",
        *(("up",) * 2),
        "left",
        *(("up",) * 8),
        *(("right",) * 10),
        "up",
    ) == VIRIDIAN_TO_MART_DIRECTIONS


def test_qualified_play_timing_defaults_are_positive_bounded_integers() -> None:
    assert QualifiedPlayTiming() == QualifiedPlayTiming(
        transition_wait_frames=120,
        rival_trigger_wait_frames=360,
        battle_wait_frames=180,
        dialogue_wait_frames=240,
        route_1_north_seed_wait_frames=192,
        mart_prompt_wait_frames=240,
        route_1_south_seed_wait_frames=48,
        max_rival_pulses=56,
        max_parcel_pulses=5,
        max_pokedex_pulses=42,
    )
    assert QualifiedPlayTiming() == DEFAULT_QUALIFIED_PLAY_TIMING
    assert fields(QualifiedPlayTiming)
    assert all(
        isinstance(getattr(DEFAULT_QUALIFIED_PLAY_TIMING, field.name), int)
        and not isinstance(getattr(DEFAULT_QUALIFIED_PLAY_TIMING, field.name), bool)
        and getattr(DEFAULT_QUALIFIED_PLAY_TIMING, field.name) > 0
        for field in fields(QualifiedPlayTiming)
    )


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_qualified_play_timing_rejects_unbounded_values(invalid: object) -> None:
    for field in fields(QualifiedPlayTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(
                DEFAULT_QUALIFIED_PLAY_TIMING,
                **{field.name: invalid},
            )


def test_qualified_play_progress_is_sanitized_and_immutable() -> None:
    assert QUALIFIED_PLAY_CHECKPOINT_COUNT == 11
    progress = QualifiedPlayProgress(
        checkpoint_id="pokedex_obtained",
        label="Delivered Oak's Parcel and received the Pokédex",
        completed=11,
        total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
        frames_executed=52_956,
    )

    assert progress.completed == progress.total == 11
    assert progress.frames_executed == 52_956
    with pytest.raises(FrozenInstanceError):
        progress.completed = 10  # type: ignore[misc]


def test_qualified_play_report_is_complete_honest_and_privacy_safe() -> None:
    rom = RomFingerprint(
        filename="/private/home/Pokemon Red.gb",
        title="POKEMON RED",
        size_bytes=1_048_576,
        sha1="1" * 40,
        sha256="2" * 64,
    )
    opening = OpeningChapterReport(
        rom=rom,
        pyboy_version="2.7.0",
        emulator_window="SDL2",
        emulator_speed=4,
        clean_power_on=True,
        bedroom=_raw(
            MapId.REDS_HOUSE_2F,
            3,
            6,
            party_count=0,
            party_species_ids=(),
        ),
        downstairs=_raw(
            MapId.REDS_HOUSE_1F,
            7,
            1,
            party_count=0,
            party_species_ids=(),
        ),
        outside=_raw(
            MapId.PALLET_TOWN,
            5,
            6,
            party_count=0,
            party_species_ids=(),
        ),
        oak_triggered=_raw(
            MapId.PALLET_TOWN,
            10,
            1,
            party_count=0,
            party_species_ids=(),
        ),
        selection_ready=_raw(
            MapId.OAKS_LAB,
            5,
            3,
            party_count=0,
            party_species_ids=(),
        ),
        starter=_raw(MapId.OAKS_LAB, 7, 4),
        selection_control=_opening_control(OpeningPhase.STARTER_SELECTION_READY),
        starter_control=_opening_control(
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
        frames_executed=21_216,
        actions_executed=178,
        controller_released=True,
    )
    report = QualifiedPlayReport(
        rom=rom,
        pyboy_version="2.7.0",
        emulator_window="SDL2",
        emulator_speed=4,
        opening=opening,
        rival_defeated=_raw(MapId.OAKS_LAB, 5, 6),
        viridian_reached=_raw(MapId.VIRIDIAN_CITY, 21, 35),
        parcel_received=_raw(MapId.VIRIDIAN_MART, 2, 5),
        pallet_returned=_raw(MapId.PALLET_TOWN, 10, 0),
        pokedex_received=_raw(MapId.OAKS_LAB, 5, 3),
        rival_evidence=_rival_victory(),
        parcel_evidence=_parcel_obtained(),
        pokedex_evidence=_pokedex_obtained(),
        saw_trainer_battle=True,
        facts=frozenset(
            {
                "system:clean_power_on",
                "story:adventure_begun",
                "party:starter_obtained",
                "story:pokedex_received",
            }
        ),
        verified_objectives=(
            "power_on",
            "begin_adventure",
            "choose_starter",
            "receive_pokedex",
        ),
        next_objective="reach_pewter",
        frames_executed=52_956,
        actions_executed=619,
        controller_released=True,
    )

    public = report.public_dict()
    serialized = json.dumps(public, sort_keys=True)

    assert report.passed
    assert public["schema"] == "qualified-play-v1"
    assert public["status"] == "ok"
    assert public["qualified_through"] == "receive_pokedex"
    assert public["game_complete"] is False
    assert public["safe_stop_reason"] == "latest_qualified_boundary"
    assert [checkpoint["id"] for checkpoint in public["checkpoints"]] == [
        "bedroom_ready",
        "downstairs",
        "outside",
        "oak_triggered",
        "selection_ready",
        "starter_obtained",
        "rival_defeated",
        "viridian_reached",
        "parcel_received",
        "pallet_returned",
        "pokedex_received",
    ]
    assert public["objective_progress"] == {
        "verified": 4,
        "total": 36,
        "verified_ids": [
            "power_on",
            "begin_adventure",
            "choose_starter",
            "receive_pokedex",
        ],
        "next": "reach_pewter",
    }
    assert public["rival"]["trainer_battle_observed"] is True
    assert public["rival"]["victory_verified"] is True
    assert public["parcel"] == {
        "received_verified": True,
        "delivered_verified": True,
        "present_after_delivery": False,
    }
    assert public["pokedex"] == {
        "received_verified": True,
        "controls_ready": True,
    }
    for private_key in (
        "/private",
        "Pokemon Red.gb",
        "filename",
        "event_flags",
        "bag_item_ids",
        "party_species_ids",
        "battle_result",
        "joy_ignore",
        "lab_script",
        "mart_script",
    ):
        assert private_key not in serialized


@pytest.mark.parametrize(
    ("changes", "saw_trainer_battle"),
    (
        ({}, False),
        ({"phase": OaksErrandPhase.UNKNOWN}, True),
        ({"map_id": MapId.PALLET_TOWN}, True),
        ({"battle_state": 2}, True),
        ({"joy_ignore": 1}, True),
        ({"lab_script": 12}, True),
        ({"battled_rival": False}, True),
        ({"battle_result": 1}, True),
        ({"first_party_species": 0xB0}, True),
        ({"first_party_level": 5}, True),
        ({"first_party_hp": 0}, True),
        ({"first_party_max_hp": 22}, True),
    ),
)
def test_rival_victory_gate_rejects_every_near_miss(
    changes: dict[str, object],
    saw_trainer_battle: bool,
) -> None:
    state = replace(_rival_victory(), **changes)

    assert not is_rival_victory_verified(
        state,
        saw_trainer_battle=saw_trainer_battle,
    )


def test_rival_victory_requires_observed_entry_and_exact_result() -> None:
    victory = _rival_victory()

    assert is_rival_victory_verified(victory, saw_trainer_battle=True)
    assert not is_rival_victory_verified(victory, saw_trainer_battle=False)
    assert not is_rival_victory_verified(
        replace(victory, battle_result=2),
        saw_trainer_battle=True,
    )


def test_captured_rival_checkpoint_survives_later_wild_escape_result() -> None:
    captured = _rival_victory()
    later_observation = replace(captured, battle_result=2)

    assert is_rival_victory_verified(captured, saw_trainer_battle=True)
    assert not is_rival_victory_verified(
        later_observation,
        saw_trainer_battle=True,
    )
    assert captured.battle_result == 0
    with pytest.raises(FrozenInstanceError):
        captured.battle_result = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    (
        {"phase": OaksErrandPhase.UNKNOWN},
        {"map_id": MapId.VIRIDIAN_CITY},
        {"battle_state": 1},
        {"joy_ignore": 1},
        {"mart_script": 1},
        {"got_oaks_parcel": False},
        {"parcel_in_bag": False},
    ),
)
def test_parcel_gate_requires_the_full_conjunction(changes: dict[str, object]) -> None:
    assert not is_parcel_verified(replace(_parcel_obtained(), **changes))


def test_parcel_gate_accepts_only_the_stable_mart_snapshot() -> None:
    assert is_parcel_verified(_parcel_obtained())


@pytest.mark.parametrize(
    "changes",
    (
        {"phase": OaksErrandPhase.UNKNOWN},
        {"map_id": MapId.PALLET_TOWN},
        {"battle_state": 1},
        {"joy_ignore": 1},
        {"lab_script": 16},
        {"got_oaks_parcel": False},
        {"oak_got_parcel": False},
        {"got_pokedex": False},
        {"parcel_in_bag": True},
        {"first_party_species": 0xB0},
    ),
)
def test_pokedex_gate_requires_the_full_conjunction(changes: dict[str, object]) -> None:
    assert not is_pokedex_verified(replace(_pokedex_obtained(), **changes))


def test_pokedex_gate_accepts_stable_delivery_after_escape_result_overwrite() -> None:
    assert is_pokedex_verified(_pokedex_obtained())


def _adjacent_artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.integration
def test_private_rom_reaches_verified_pokedex_without_adjacent_artifacts() -> None:
    raw_path = os.environ.get("POKEMON_RED_ROM")
    if not raw_path:
        pytest.skip("Set POKEMON_RED_ROM to run the private integration test")

    rom_path = Path(raw_path).expanduser().resolve()
    adjacent = tuple(Path(f"{rom_path}{suffix}") for suffix in (".ram", ".rtc", ".state"))
    before = tuple(_adjacent_artifact_identity(path) for path in adjacent)

    report = run_qualified_play(rom_path)

    after = tuple(_adjacent_artifact_identity(path) for path in adjacent)
    assert report.passed
    assert report.verified_objectives == (
        "power_on",
        "begin_adventure",
        "choose_starter",
        "receive_pokedex",
    )
    assert report.next_objective == "reach_pewter"
    assert report.frames_executed == 52_956
    assert report.actions_executed == 619
    assert before == after
