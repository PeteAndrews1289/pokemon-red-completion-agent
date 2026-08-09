from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from pokemon_red_completion.observation import (
    BROCK_GYM_LEADER_NUMBER,
    BROCK_OPPONENT_ID,
    BROCK_TRAINER_CLASS_ID,
    BUBBLE_MOVE_ID,
    SQUIRTLE_SPECIES_ID,
    InputReadiness,
    ItemId,
    MapId,
    NorthboundPhase,
    OaksErrandPhase,
    OaksErrandState,
    PewterChapterState,
    RawGameState,
    TravelBoundary,
)
from pokemon_red_completion.pewter import (
    DEFAULT_PEWTER_TIMING,
    FOREST_ROUTE_DIRECTIONS,
    GYM_TO_BROCK_DIRECTIONS,
    LAB_TO_PALLET_DIRECTIONS,
    PEWTER_CHECKPOINT_COUNT,
    PEWTER_TO_GYM_DIRECTIONS,
    ROUTE_1_TO_VIRIDIAN_DIRECTIONS,
    ROUTE_2_TO_FOREST_GATE_DIRECTIONS,
    VIRIDIAN_TO_ROUTE_2_DIRECTIONS,
    PewterChapterReport,
    PewterProgress,
    PewterTiming,
)


def _raw(
    map_id: MapId,
    x: int,
    y: int,
    *,
    level: int = 9,
    hp: int = 21,
    max_hp: int = 27,
    battle_state: int = 0,
    badge_bits: int = 0,
    bag: tuple[int, ...] = (),
    bubble_pp: int = 26,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=int(map_id),
        player_x=x,
        player_y=y,
        party_count=1,
        battle_state=battle_state,
        badge_bits=badge_bits,
        bag_item_ids=bag,
        event_flags=b"",
        party_species_ids=(SQUIRTLE_SPECIES_ID,),
        first_party_level=level,
        first_party_hp=hp,
        first_party_max_hp=max_hp,
        first_party_status=0,
        battle_result=0,
        first_party_moves=(0x21, 0x27, BUBBLE_MOVE_ID, 0),
        first_party_pp=(4, 30, bubble_pp, 0),
    )


def _pokedex() -> OaksErrandState:
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
        battle_result=2,
        map_id=MapId.OAKS_LAB,
        battle_state=0,
    )


def _gym_ready() -> PewterChapterState:
    return PewterChapterState(
        phase=NorthboundPhase.PEWTER_GYM_ENTERED,
        boundary=TravelBoundary.PEWTER_GYM_ENTRANCE,
        controls=InputReadiness(0, 0, 0, 0, 0, 0),
        local_script=0,
        current_map_script=0,
        oak_lab_script=18,
        got_oaks_parcel=True,
        oak_got_parcel=True,
        got_pokedex=True,
        parcel_in_bag=False,
        beat_brock=False,
        got_tm34=False,
        tm34_in_bag=False,
        boulder_badge=False,
        boulder_badge_mirror=False,
        current_opponent=0,
        trainer_class=0,
        engaged_trainer_class=0,
        gym_leader_number=0,
        map_id=MapId.PEWTER_GYM,
        player_x=4,
        player_y=13,
        party_count=1,
        first_party_species=SQUIRTLE_SPECIES_ID,
        first_party_hp=21,
        first_party_max_hp=27,
        first_party_level=9,
        battle_state=0,
        battle_result=2,
        first_party_status=0,
        first_party_moves=(0x21, 0x27, BUBBLE_MOVE_ID, 0),
        first_party_pp=(4, 30, 26, 0),
    )


def _brock_battle() -> PewterChapterState:
    return replace(
        _gym_ready(),
        phase=NorthboundPhase.BROCK_BATTLE,
        boundary=TravelBoundary.UNKNOWN,
        local_script=3,
        current_map_script=3,
        current_opponent=BROCK_OPPONENT_ID,
        trainer_class=BROCK_TRAINER_CLASS_ID,
        engaged_trainer_class=BROCK_OPPONENT_ID,
        gym_leader_number=BROCK_GYM_LEADER_NUMBER,
        player_y=2,
        battle_state=2,
    )


def _brock_victory() -> PewterChapterState:
    return replace(
        _gym_ready(),
        phase=NorthboundPhase.BROCK_DEFEATED,
        boundary=TravelBoundary.UNKNOWN,
        beat_brock=True,
        got_tm34=True,
        tm34_in_bag=True,
        boulder_badge=True,
        boulder_badge_mirror=True,
        player_y=2,
        first_party_hp=27,
        first_party_max_hp=33,
        first_party_level=12,
        battle_result=0,
        first_party_pp=(4, 30, 23, 0),
    )


def _report() -> PewterChapterReport:
    gym_ready = _gym_ready()
    brock_battle = _brock_battle()
    brock_victory = _brock_victory()
    return PewterChapterReport(
        pokedex_evidence=_pokedex(),
        lab_exited=_raw(MapId.PALLET_TOWN, 12, 12, level=6, max_hp=21),
        viridian_reached=_raw(MapId.VIRIDIAN_CITY, 21, 35, level=6, max_hp=21),
        route_2_reached=_raw(MapId.ROUTE_2, 8, 71, level=6, max_hp=21),
        forest_gate_reached=_raw(
            MapId.VIRIDIAN_FOREST_SOUTH_GATE,
            4,
            7,
            level=6,
            max_hp=21,
        ),
        forest_entered=_raw(MapId.VIRIDIAN_FOREST, 17, 47, level=6, max_hp=21),
        forest_cleared=_raw(MapId.VIRIDIAN_FOREST_NORTH_GATE, 4, 7),
        pewter_reached=_raw(MapId.PEWTER_CITY, 18, 35),
        gym_entered=_raw(MapId.PEWTER_GYM, 4, 13),
        brock_battle=_raw(MapId.PEWTER_GYM, 4, 2, battle_state=2),
        brock_defeated=_raw(
            MapId.PEWTER_GYM,
            4,
            2,
            level=12,
            hp=27,
            max_hp=33,
            badge_bits=1,
            bag=(ItemId.TM34_BIDE,),
            bubble_pp=23,
        ),
        gym_entry_evidence=gym_ready,
        brock_battle_evidence=brock_battle,
        brock_victory_evidence=brock_victory,
        reached_boundaries=tuple(TravelBoundary)[1:],
        saw_brock_battle=True,
        route_1_wild_flees=(),
        route_1_movement_retries=0,
        overworld_control_verified=True,
        frames_executed=70_043,
        actions_executed=954,
        controller_released=True,
    )


def test_pewter_route_is_source_stable_at_critical_segments() -> None:
    assert LAB_TO_PALLET_DIRECTIONS == ("down",) * 9
    assert len(ROUTE_1_TO_VIRIDIAN_DIRECTIONS) == 53
    assert len(VIRIDIAN_TO_ROUTE_2_DIRECTIONS) == 39
    assert len(ROUTE_2_TO_FOREST_GATE_DIRECTIONS) == 43
    assert len(FOREST_ROUTE_DIRECTIONS) == 135
    assert FOREST_ROUTE_DIRECTIONS[97:117] == (
        *(("down",) * 9),
        *(("left",) * 6),
        *(("up",) * 3),
        "left",
        "up",
    )
    assert len(PEWTER_TO_GYM_DIRECTIONS) == 44
    assert len(GYM_TO_BROCK_DIRECTIONS) == 17


def test_pewter_timing_defaults_are_positive_bounded_integers() -> None:
    assert PewterTiming() == DEFAULT_PEWTER_TIMING
    assert fields(PewterTiming)
    assert all(
        isinstance(getattr(DEFAULT_PEWTER_TIMING, field.name), int)
        and not isinstance(getattr(DEFAULT_PEWTER_TIMING, field.name), bool)
        and getattr(DEFAULT_PEWTER_TIMING, field.name) > 0
        for field in fields(PewterTiming)
    )


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_pewter_timing_rejects_unbounded_values(invalid: object) -> None:
    for field in fields(PewterTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_PEWTER_TIMING, **{field.name: invalid})


def test_pewter_progress_is_sanitized_and_immutable() -> None:
    progress = PewterProgress(
        checkpoint_id="brock_defeated",
        label="Defeated Brock and received TM34",
        completed=PEWTER_CHECKPOINT_COUNT,
        total=PEWTER_CHECKPOINT_COUNT,
        frames_executed=122_999,
    )

    assert progress.completed == progress.total == 10
    with pytest.raises(FrozenInstanceError):
        progress.completed = 9  # type: ignore[misc]


def test_pewter_report_is_complete_honest_and_privacy_safe() -> None:
    report = _report()

    public = report.public_dict()
    serialized = json.dumps(public, sort_keys=True)

    assert report.passed
    assert public["status"] == "ok"
    assert len(public["checkpoints"]) == PEWTER_CHECKPOINT_COUNT
    assert public["route"] == {
        "ordered_boundaries_verified": 9,
        "ordered_boundaries_total": 9,
        "brock_battle_observed": True,
        "route_1_wild_flees": [],
        "route_1_movement_retries": 0,
    }
    assert public["brock"] == {
        "victory_verified": True,
        "boulder_badge_verified": True,
        "tm34_verified": True,
        "overworld_control_verified": True,
        "squirtle_level": 12,
        "squirtle_hp": 27,
        "squirtle_max_hp": 33,
        "squirtle_status": 0,
        "bubble_pp": 23,
    }
    for private_key in (
        "event_flags",
        "bag_item_ids",
        "party_species_ids",
        "first_party_moves",
        "first_party_pp",
        "joy_ignore",
        "current_opponent",
        "trainer_class",
    ):
        assert private_key not in serialized


@pytest.mark.parametrize(
    "changes",
    (
        {"saw_brock_battle": False},
        {"overworld_control_verified": False},
        {"controller_released": False},
        {"reached_boundaries": tuple(TravelBoundary)[1:-1]},
        {"gym_entry_evidence": replace(_gym_ready(), first_party_hp=18)},
        {
            "brock_battle_evidence": replace(
                _brock_battle(),
                current_opponent=0,
            )
        },
        {"brock_victory_evidence": replace(_brock_victory(), got_tm34=False)},
        {
            "brock_defeated": replace(
                _report().brock_defeated,
                bag_item_ids=(),
            )
        },
    ),
)
def test_pewter_report_rejects_each_evidence_near_miss(
    changes: dict[str, object],
) -> None:
    assert not replace(_report(), **changes).passed
