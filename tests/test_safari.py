from __future__ import annotations

from dataclasses import fields, replace

import pytest

from pokemon_red_completion.observation import EventFlag, ItemId, MapId, RamAddress, RawGameState
from pokemon_red_completion.safari import (
    DEFAULT_SAFARI_TIMING,
    EXPECTED_MOVES_AFTER,
    EXPECTED_MOVES_BEFORE,
    EXPECTED_PP_AFTER,
    GOLD_TEETH_CHECKPOINT_COUNT,
    POST_SILPH_MOVES_AFTER_SURF,
    POST_SILPH_MOVES_BEFORE_SURF,
    POST_SILPH_PP_AFTER_SURF,
    SAFARI_CHECKPOINT_COUNT,
    GoldTeethChapterReport,
    SafariChapterReport,
    SafariCheckpoint,
    SafariTiming,
)


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.FUCHSIA_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=3,
        battle_state=0,
        party_species_ids=(0x1C, 0x40, 0x3B),
        first_party_level=37,
        first_party_hp=114,
        first_party_max_hp=114,
        first_party_status=0,
        first_party_moves=EXPECTED_MOVES_AFTER,
        first_party_pp=EXPECTED_PP_AFTER,
    )


def _report() -> SafariChapterReport:
    raw = _raw()
    initial_bag = ((0x04, 8), (0x28, 1), (0x49, 1))
    final_bag = tuple(
        sorted(
            (
                *initial_bag,
                (int(ItemId.GOLD_TEETH), 1),
                (int(ItemId.HM03_SURF), 1),
                (int(ItemId.TM40_SKULL_BASH), 1),
            )
        )
    )
    return SafariChapterReport(
        records=tuple(
            SafariCheckpoint(f"gate_{index}", f"Gate {index}", raw, 0, 0)
            for index in range(SAFARI_CHECKPOINT_COUNT)
        ),
        final_raw=raw,
        initial_bag=initial_bag,
        final_bag=final_bag,
        initial_money=25_839,
        final_money=25_339,
        counter_milestones=(500, 472, 376, 238, 228, 201, 0),
        balls_milestones=(30,) * 7,
        got_tm40_skull_bash=True,
        gold_teeth=True,
        gold_teeth_precollected=False,
        got_hm03=True,
        hm03_retained=True,
        in_safari_zone=False,
        safari_steps=0,
        safari_balls=0,
        capacity_ready=True,
        moves_before=EXPECTED_MOVES_BEFORE,
        moves_after=EXPECTED_MOVES_AFTER,
        pp_before=(16, 30, 16, 25),
        pp_after_teach=(16, 30, 16, 15),
        pp_after=EXPECTED_PP_AFTER,
        encounters_fled=6,
        party_hp=(114, 52, 37),
        party_max_hp=(114, 52, 37),
        party_status=(0, 0, 0),
        frames_executed=190_000,
        actions_executed=1_200,
        controller_released=True,
    )


def _gold_teeth_report() -> GoldTeethChapterReport:
    raw = replace(
        _raw(),
        first_party_moves=EXPECTED_MOVES_BEFORE,
        first_party_pp=(25, 30, 20, 25),
    )
    initial_bag = ((0x04, 8), (0x28, 1), (0x49, 1))
    final_bag = tuple(
        sorted(
            (
                *initial_bag,
                (int(ItemId.GOLD_TEETH), 1),
                (int(ItemId.TM40_SKULL_BASH), 1),
            )
        )
    )
    return GoldTeethChapterReport(
        records=tuple(
            SafariCheckpoint(f"gate_{index}", f"Gate {index}", raw, 0, 0)
            for index in range(GOLD_TEETH_CHECKPOINT_COUNT)
        ),
        final_raw=raw,
        initial_bag=initial_bag,
        final_bag=final_bag,
        initial_money=25_839,
        final_money=25_339,
        counter_milestones=(500, 472, 376, 238, 228, 0),
        balls_milestones=(30,) * 6,
        got_tm40_skull_bash=True,
        gold_teeth=True,
        got_hm03=False,
        in_safari_zone=False,
        safari_steps=0,
        safari_balls=0,
        moves_before=EXPECTED_MOVES_BEFORE,
        moves_after=EXPECTED_MOVES_BEFORE,
        pp_after=(25, 30, 20, 25),
        encounters_fled=5,
        party_hp=(114, 52, 37),
        party_max_hp=(114, 52, 37),
        party_status=(0, 0, 0),
        frames_executed=180_000,
        actions_executed=1_100,
        controller_released=True,
    )


def test_safari_timing_is_positive_and_bounded() -> None:
    assert SafariTiming() == DEFAULT_SAFARI_TIMING
    assert all(
        isinstance(getattr(DEFAULT_SAFARI_TIMING, field.name), int)
        and getattr(DEFAULT_SAFARI_TIMING, field.name) > 0
        for field in fields(SafariTiming)
    )


def test_safari_report_accepts_exact_post_silph_surf_lineage() -> None:
    report = _report()
    initial_bag = tuple(sorted((*report.initial_bag, (int(ItemId.TM40_SKULL_BASH), 1))))
    final_bag = tuple(sorted((*initial_bag, (int(ItemId.HM03_SURF), 1))))
    raw = replace(
        report.final_raw,
        first_party_moves=POST_SILPH_MOVES_AFTER_SURF,
        first_party_pp=POST_SILPH_PP_AFTER_SURF,
    )
    qualified = replace(
        report,
        final_raw=raw,
        initial_bag=initial_bag,
        final_bag=final_bag,
        gold_teeth=False,
        gold_teeth_precollected=True,
        moves_before=POST_SILPH_MOVES_BEFORE_SURF,
        moves_after=POST_SILPH_MOVES_AFTER_SURF,
        pp_before=(25, 15, 10, 25),
        pp_after_teach=POST_SILPH_PP_AFTER_SURF,
        pp_after=POST_SILPH_PP_AFTER_SURF,
    )

    assert qualified.passed
    assert not replace(
        qualified,
        moves_before=(0x2C, 0x46, 0x01, 0x37),
    ).passed


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_safari_timing_rejects_invalid_bounds(invalid: object) -> None:
    for field in fields(SafariTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_SAFARI_TIMING, **{field.name: invalid})


def test_safari_report_requires_every_terminal_gate() -> None:
    report = _report()
    assert report.passed
    invalid = (
        replace(report, records=report.records[:-1]),
        replace(report, final_money=25_538),
        replace(report, counter_milestones=(500, 472, 376, 238, 228, 200, 0)),
        replace(report, balls_milestones=(30, 30, 29, 30, 30, 30, 30)),
        replace(report, got_tm40_skull_bash=False),
        replace(report, gold_teeth=False),
        replace(report, got_hm03=False),
        replace(report, hm03_retained=False),
        replace(report, in_safari_zone=True),
        replace(report, safari_steps=1),
        replace(report, safari_balls=30),
        replace(report, moves_after=(0x39, 0x27, 0x3D, 0x37)),
        replace(report, pp_after=(25, 30, 20, 25)),
        replace(report, encounters_fled=21),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid)


def test_safari_public_report_discloses_one_admission_and_reusable_hm() -> None:
    public = _report().public_dict()
    assert public["status"] == "ok"
    assert public["objective"] == "obtain_surf"
    assert public["admission"] == {
        "fee": 500,
        "initial_steps": 500,
        "initial_balls": 30,
        "single_admission": True,
    }
    assert public["rewards"]["hm03_reusable_and_retained"] is True
    assert public["rewards"]["tm40_skull_bash"] is True
    assert public["surf"]["slot"] == 4
    assert public["cleanup"]["mechanism"] == "times_up"


def test_gold_teeth_report_proves_hm03_was_not_obtained() -> None:
    report = _gold_teeth_report()

    assert report.passed
    assert report.public_dict()["resource"] == "gold_teeth"
    assert report.public_dict()["objective_added"] is False
    assert report.public_dict()["rewards"] == {
        "tm40_skull_bash": True,
        "gold_teeth": True,
        "hm03_untouched": True,
    }
    assert report.public_dict()["cleanup"]["mechanism"] == "times_up_before_secret_house"


def test_gold_teeth_report_rejects_surf_or_incomplete_cleanup() -> None:
    report = _gold_teeth_report()
    invalid = (
        replace(report, records=report.records[:-1]),
        replace(report, got_hm03=True),
        replace(report, moves_after=EXPECTED_MOVES_AFTER),
        replace(report, pp_after=EXPECTED_PP_AFTER),
        replace(report, counter_milestones=(500, 472, 376, 238, 228, 1)),
        replace(report, safari_steps=1),
        replace(report, controller_released=False),
    )

    assert all(not candidate.passed for candidate in invalid)


def test_safari_source_addresses_and_ids_are_pinned() -> None:
    assert RamAddress.SAFARI_STEPS == 0xD70D
    assert RamAddress.SAFARI_BALLS == 0xDA47
    assert EventFlag.SAFARI_GAME_OVER == 0x24E
    assert EventFlag.IN_SAFARI_ZONE == 0x24F
    assert EventFlag.GOT_HM03 == 0x880
    assert ItemId.GOLD_TEETH == 0x40
    assert ItemId.HM03_SURF == 0xC6
    assert ItemId.TM40_SKULL_BASH == 0xF0
    assert MapId.SAFARI_ZONE_GATE == 0x9C
    assert MapId.SAFARI_ZONE_EAST == 0xD9
    assert MapId.SAFARI_ZONE_NORTH == 0xDA
    assert MapId.SAFARI_ZONE_WEST == 0xDB
    assert MapId.SAFARI_ZONE_CENTER == 0xDC
    assert MapId.SAFARI_ZONE_SECRET_HOUSE == 0xDE
