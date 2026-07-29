from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace
from typing import cast

import pytest

from pokemon_red_completion.cascade import (
    BILL_EXIT_DIRECTIONS,
    BILL_PC_TO_HUMAN_DIRECTIONS,
    BILL_RETURN_WAIT_SEGMENTS,
    BILL_TO_CENTER_SEGMENTS,
    CASCADE_CHECKPOINT_COUNT,
    CENTER_TO_RIVAL_STAGING_DIRECTIONS,
    CENTER_TO_ROUTE_24_STAGING_CORRECTION_DIRECTIONS,
    DEFAULT_CASCADE_TIMING,
    GYM_TRAINER_DIRECTIONS,
    GYM_TRAINER_TO_MISTY_DIRECTIONS,
    RIVAL_CENTER_NPC_CORRECTION_DIRECTIONS,
    RIVAL_TRIGGER_DIRECTIONS,
    ROUTE_24_REQUIRED_TRAINER_INDEXES,
    ROUTE_24_TRAINER_SEGMENTS,
    ROUTE_25_REQUIRED_TRAINER_INDEXES,
    ROUTE_25_TRAINER_SEGMENTS,
    CascadeChapterReport,
    CascadeCheckpoint,
    CascadeProgress,
    CascadeTiming,
    _reverse_directions,
)
from pokemon_red_completion.observation import (
    WARTORTLE_SPECIES_ID,
    CascadeState,
    CeruleanChapterState,
    MapId,
    RawGameState,
)


class _StartingEvidence:
    cerulean_snapshot = True


class _FinalEvidence:
    misty_victory_snapshot = True
    cascade_badge = True
    cascade_badge_mirror = True
    got_tm11 = True
    tm11_in_bag = True
    got_ss_ticket = True
    ss_ticket_in_bag = True


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.CERULEAN_GYM,
        player_x=5,
        player_y=2,
        party_count=1,
        battle_state=0,
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_level=24,
        first_party_hp=18,
        first_party_max_hp=66,
        first_party_status=0,
        battle_result=0,
    )


def _report() -> CascadeChapterReport:
    raw = _raw()
    evidence = cast(CascadeState, _FinalEvidence())
    records = tuple(
        CascadeCheckpoint(
            checkpoint_id=f"cascade_{index:02d}",
            label=f"Cascade checkpoint {index}",
            raw=raw,
            evidence=evidence,
        )
        for index in range(1, CASCADE_CHECKPOINT_COUNT + 1)
    )
    return CascadeChapterReport(
        starting_cerulean_evidence=cast(
            CeruleanChapterState,
            _StartingEvidence(),
        ),
        records=records,
        final_raw=raw,
        final_evidence=evidence,
        observed_route_24_trainers=ROUTE_24_REQUIRED_TRAINER_INDEXES,
        observed_route_25_trainers=ROUTE_25_REQUIRED_TRAINER_INDEXES,
        saw_rival_battle=True,
        rival_defeated=True,
        saw_nugget_rocket_battle=True,
        nugget_rocket_defeated=True,
        bills_house_left=True,
        saw_cerulean_gym_trainer_battle=True,
        cerulean_gym_trainer_defeated=True,
        saw_misty_battle=True,
        misty_defeated=True,
        frames_executed=141_000,
        actions_executed=2_100,
        controller_released=True,
    )


def test_route_constants_capture_the_collision_qualified_teacher() -> None:
    assert ROUTE_24_REQUIRED_TRAINER_INDEXES == (5, 4, 3, 2, 1)
    assert tuple(len(segment) for segment in ROUTE_24_TRAINER_SEGMENTS) == (
        4,
        4,
        4,
        4,
        4,
    )
    assert ROUTE_25_REQUIRED_TRAINER_INDEXES == (8, 3, 2, 5)
    assert tuple(len(segment) for segment in ROUTE_25_TRAINER_SEGMENTS) == (
        20,
        12,
        6,
        14,
    )
    assert len(CENTER_TO_RIVAL_STAGING_DIRECTIONS) == 34
    assert CENTER_TO_ROUTE_24_STAGING_CORRECTION_DIRECTIONS == ("left",)
    assert RIVAL_TRIGGER_DIRECTIONS == ("up",)
    assert RIVAL_CENTER_NPC_CORRECTION_DIRECTIONS == (
        "down",
        "right",
        "right",
        "right",
        "up",
    )
    assert BILL_PC_TO_HUMAN_DIRECTIONS == (
        "right",
        "right",
        "right",
        "up",
    )
    assert BILL_EXIT_DIRECTIONS == ("down", "left", "down", "down")
    assert tuple(len(segment) for segment in BILL_TO_CENTER_SEGMENTS) == (
        9,
        14,
        6,
        12,
        20,
        17,
        4,
        4,
        4,
        4,
        4,
        4,
        1,
        42,
    )
    assert frozenset({6, 13, 14}) == BILL_RETURN_WAIT_SEGMENTS
    assert len(GYM_TRAINER_DIRECTIONS) == 19
    assert GYM_TRAINER_TO_MISTY_DIRECTIONS == ("up", "left")


def test_reverse_directions_is_exact_and_involutive() -> None:
    route = ("up", "right", "right", "down", "left")
    reversed_route = _reverse_directions(route)

    assert reversed_route == ("right", "up", "left", "left", "down")
    assert _reverse_directions(reversed_route) == route


def test_cascade_timing_defaults_are_positive_and_pin_qualified_delays() -> None:
    assert CascadeTiming() == DEFAULT_CASCADE_TIMING
    assert DEFAULT_CASCADE_TIMING.rival_seed_wait_frames == 41
    assert DEFAULT_CASCADE_TIMING.misty_seed_wait_frames == 2
    assert DEFAULT_CASCADE_TIMING.post_battle_cleanup_pulses == 1
    assert DEFAULT_CASCADE_TIMING.gym_trainer_cleanup_pulses == 3
    assert DEFAULT_CASCADE_TIMING.bill_ticket_cleanup_pulses == 9
    assert DEFAULT_CASCADE_TIMING.misty_reward_pulses == 9
    assert DEFAULT_CASCADE_TIMING.max_route_24_npc_attempts == 4
    for field in fields(CascadeTiming):
        if field.name == "battle_runtime":
            continue
        value = getattr(DEFAULT_CASCADE_TIMING, field.name)
        assert isinstance(value, int)
        assert not isinstance(value, bool)
        assert value > 0


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_cascade_timing_rejects_unbounded_scalar_values(invalid: object) -> None:
    for field in fields(CascadeTiming):
        if field.name == "battle_runtime":
            continue
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_CASCADE_TIMING, **{field.name: invalid})


def test_cascade_timing_rejects_a_non_runtime_battle_controller() -> None:
    with pytest.raises(ValueError, match="battle_runtime"):
        replace(DEFAULT_CASCADE_TIMING, battle_runtime=object())


def test_progress_and_checkpoint_records_are_immutable() -> None:
    progress = CascadeProgress(
        checkpoint_id="misty_defeated",
        label="Defeated Misty",
        completed=CASCADE_CHECKPOINT_COUNT,
        total=CASCADE_CHECKPOINT_COUNT,
        frames_executed=141_000,
    )
    record = _report().records[-1]

    with pytest.raises(FrozenInstanceError):
        progress.completed = 0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        record.label = "changed"  # type: ignore[misc]


def test_report_is_complete_honest_and_json_safe() -> None:
    report = _report()

    assert report.passed
    assert len(report.checkpoints()) == CASCADE_CHECKPOINT_COUNT
    assert report.checkpoints()[-1][2] is report.final_raw
    payload = report.public_dict()
    assert payload["status"] == "ok"
    assert payload["route"] == {
        "route_24_trainers": [5, 4, 3, 2, 1],
        "route_25_trainers": [8, 3, 2, 5],
        "rival_battle_observed": True,
        "nugget_rocket_battle_observed": True,
        "bill_help_verified": True,
        "gym_trainer_battle_observed": True,
        "misty_battle_observed": True,
    }
    assert payload["cascade"] == {
        "victory_verified": True,
        "badge_verified": True,
        "tm11_verified": True,
        "ss_ticket_verified": True,
        "wartortle_level": 24,
        "wartortle_hp": 18,
        "wartortle_max_hp": 66,
        "wartortle_status": 0,
    }
    assert "/Users/" not in json.dumps(payload)


@pytest.mark.parametrize(
    "change",
    (
        {"records": ()},
        {"observed_route_24_trainers": (5, 4, 3, 2)},
        {"observed_route_25_trainers": (8, 3, 2)},
        {"saw_cerulean_gym_trainer_battle": False},
        {"cerulean_gym_trainer_defeated": False},
        {"misty_defeated": False},
        {"controller_released": False},
    ),
)
def test_report_rejects_missing_or_skipped_evidence(
    change: dict[str, object],
) -> None:
    assert not replace(_report(), **change).passed
