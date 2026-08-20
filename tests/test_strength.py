from __future__ import annotations

from dataclasses import fields, replace

import pytest

from pokemon_red_completion.observation import EventFlag, ItemId, MapId, RawGameState
from pokemon_red_completion.strength import (
    CENTER_EXIT,
    CITY_TO_WARDEN,
    DEFAULT_STRENGTH_TIMING,
    EXPECTED_MOVES_AFTER,
    EXPECTED_MOVES_BEFORE,
    EXPECTED_PP_AFTER,
    NATURAL_MOVES_AFTER,
    NATURAL_MOVES_BEFORE,
    NATURAL_PP_AFTER,
    PRE_SURF_MOVES_AFTER,
    PRE_SURF_MOVES_BEFORE,
    PRE_SURF_PP_AFTER,
    STRENGTH_CHECKPOINT_COUNT,
    StrengthChapterReport,
    StrengthCheckpoint,
    StrengthTiming,
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
        first_party_level=40,
        first_party_hp=124,
        first_party_max_hp=124,
        first_party_status=0,
        first_party_moves=EXPECTED_MOVES_AFTER,
        first_party_pp=EXPECTED_PP_AFTER,
    )


def _report() -> StrengthChapterReport:
    raw = _raw()
    initial_bag = ((4, 8), (int(ItemId.GOLD_TEETH), 1), (198, 1), (206, 1))
    final_bag = ((4, 8), (198, 1), (int(ItemId.HM04_STRENGTH), 1), (206, 1))
    return StrengthChapterReport(
        records=tuple(
            StrengthCheckpoint(f"gate_{index}", f"Gate {index}", raw)
            for index in range(STRENGTH_CHECKPOINT_COUNT)
        ),
        final_raw=raw,
        initial_bag=initial_bag,
        final_bag=final_bag,
        initial_money=28_191,
        final_money=28_191,
        gave_gold_teeth=True,
        got_hm04=True,
        gold_teeth_removed=True,
        hm04_retained=True,
        moves_before=EXPECTED_MOVES_BEFORE,
        moves_after=EXPECTED_MOVES_AFTER,
        pp_after=EXPECTED_PP_AFTER,
        party_hp=(124, 47, 40),
        party_max_hp=(124, 47, 40),
        party_status=(0, 0, 0),
        frames_executed=93_936,
        actions_executed=726,
        controller_released=True,
    )


def test_strength_timing_is_positive_and_bounded() -> None:
    assert StrengthTiming() == DEFAULT_STRENGTH_TIMING
    assert all(
        isinstance(getattr(DEFAULT_STRENGTH_TIMING, field.name), int)
        and getattr(DEFAULT_STRENGTH_TIMING, field.name) > 0
        for field in fields(StrengthTiming)
    )


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_strength_timing_rejects_invalid_bounds(invalid: object) -> None:
    for field in fields(StrengthTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_STRENGTH_TIMING, **{field.name: invalid})


def test_strength_report_requires_every_terminal_gate() -> None:
    report = _report()
    assert report.passed
    invalid = (
        replace(report, records=report.records[:-1]),
        replace(report, gave_gold_teeth=False),
        replace(report, got_hm04=False),
        replace(report, gold_teeth_removed=False),
        replace(report, hm04_retained=False),
        replace(report, moves_after=EXPECTED_MOVES_BEFORE),
        replace(report, pp_after=(25, 30, 20, 15)),
        replace(report, party_hp=(123, 47, 40)),
        replace(report, final_money=37_488),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid)


def test_strength_report_accepts_naturally_learned_skull_bash_lineage() -> None:
    report = _report()
    natural_raw = replace(
        report.final_raw,
        first_party_moves=NATURAL_MOVES_AFTER,
        first_party_pp=NATURAL_PP_AFTER,
    )
    natural = replace(
        report,
        final_raw=natural_raw,
        moves_before=NATURAL_MOVES_BEFORE,
        moves_after=NATURAL_MOVES_AFTER,
        pp_after=NATURAL_PP_AFTER,
    )

    assert natural.passed
    assert natural.public_dict()["strength"]["moves_before"] == list(NATURAL_MOVES_BEFORE)


def test_strength_report_accepts_gold_teeth_before_surf() -> None:
    report = _report()
    pre_surf_raw = replace(
        report.final_raw,
        first_party_moves=PRE_SURF_MOVES_AFTER,
        first_party_pp=PRE_SURF_PP_AFTER,
    )
    pre_surf = replace(
        report,
        final_raw=pre_surf_raw,
        moves_before=PRE_SURF_MOVES_BEFORE,
        moves_after=PRE_SURF_MOVES_AFTER,
        pp_after=PRE_SURF_PP_AFTER,
    )

    assert pre_surf.passed
    assert pre_surf.public_dict()["strength"]["moves_before"] == list(
        PRE_SURF_MOVES_BEFORE
    )


def test_strength_public_report_discloses_exact_reusable_hm_teaching() -> None:
    public = _report().public_dict()
    assert public["status"] == "ok"
    assert public["objective"] == "obtain_strength"
    assert public["warden"] == {
        "gold_teeth_removed": True,
        "gave_gold_teeth_event": True,
        "got_hm04_event": True,
        "hm04_reusable_and_retained": True,
    }
    assert public["strength"] == {
        "move_id": 0x46,
        "replaced_move_id": 0x27,
        "slot": 2,
        "moves_before": [0x2C, 0x27, 0x3D, 0x39],
        "moves_after": [0x2C, 0x46, 0x3D, 0x39],
        "pp_after": [25, 15, 20, 15],
    }


def test_strength_source_ids_and_routes_are_pinned() -> None:
    assert MapId.WARDENS_HOUSE == 0x9B
    assert EventFlag.GOT_HM04 == 0x238
    assert EventFlag.GAVE_GOLD_TEETH == 0x239
    assert ItemId.GOLD_TEETH == 0x40
    assert ItemId.HM04_STRENGTH == 0xC7
    assert CENTER_EXIT == ("down",) * 5
    assert len(CITY_TO_WARDEN) == 80


def test_strength_return_route_keeps_the_static_fence_detour() -> None:
    from pokemon_red_completion.strength import WARDEN_TO_CITY_CENTER

    # A direct left from Fuchsia (24, 26) is a static fence. The qualified
    # suffix turns north first and rejoins the Center approach from the west.
    assert len(WARDEN_TO_CITY_CENTER) == 176
    assert WARDEN_TO_CITY_CENTER[74:84] == ("up",) * 10
