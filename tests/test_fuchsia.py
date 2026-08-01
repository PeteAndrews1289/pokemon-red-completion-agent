from __future__ import annotations

from dataclasses import fields, replace

import pytest

from pokemon_red_completion.fuchsia import (
    DEFAULT_FUCHSIA_TIMING,
    FUCHSIA_CHECKPOINT_COUNT,
    OPTIONAL_EVENTS,
    OPTIONAL_ITEMS,
    REQUIRED_EVENTS,
    FuchsiaBattleEvidence,
    FuchsiaChapterReport,
    FuchsiaCheckpoint,
    FuchsiaTiming,
    _snorlax_move_slot,
)
from pokemon_red_completion.observation import EventFlag, MapId, RawGameState


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
        first_party_moves=(0x2C, 0x27, 0x3D, 0x37),
        first_party_pp=(25, 30, 20, 25),
    )


def _report() -> FuchsiaChapterReport:
    raw = _raw()
    sets = (3, None, 2, 1, 12)
    opponents = (0xD6, 0x84, 0xDC, 0xDF, 0xCE)
    classes = (0x0E, None, 0x14, 0x17, 0x06)
    events = tuple(int(item) for item in REQUIRED_EVENTS)
    spent = (4, 3, 4, 4, 7)
    bag = ((0x04, 8), (0x28, 1), (0x49, 1))
    return FuchsiaChapterReport(
        records=tuple(
            FuchsiaCheckpoint(f"gate_{index}", f"Gate {index}", raw)
            for index in range(FUCHSIA_CHECKPOINT_COUNT)
        ),
        battles=tuple(
            FuchsiaBattleEvidence(
                f"battle {index}",
                opponents[index],
                classes[index],
                sets[index],
                events[index],
                0x3D if index < 3 else 0x2C,
                spent[index],
                (0x84,) if index == 1 else (),
                30 if index == 1 else None,
            )
            for index in range(5)
        ),
        final_raw=raw,
        required_events=(True,) * len(REQUIRED_EVENTS),
        optional_events=(False,) * len(OPTIONAL_EVENTS),
        optional_items_carried=(False,) * len(OPTIONAL_ITEMS),
        flute_retained=True,
        snorlax_fight_before=False,
        snorlax_fight_after=False,
        snorlax_object_tile_crossed=True,
        wild_flees=4,
        initial_bag=bag,
        final_bag=bag,
        party_hp=(114, 52, 37),
        party_max_hp=(114, 52, 37),
        party_status=(0, 0, 0),
        money_remaining=25_839,
        frames_executed=277_925,
        actions_executed=2_276,
        controller_released=True,
    )


def test_fuchsia_timing_is_positive_and_bounded() -> None:
    assert FuchsiaTiming() == DEFAULT_FUCHSIA_TIMING
    assert all(
        isinstance(getattr(DEFAULT_FUCHSIA_TIMING, field.name), int)
        and getattr(DEFAULT_FUCHSIA_TIMING, field.name) > 0
        for field in fields(FuchsiaTiming)
    )


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_fuchsia_timing_rejects_invalid_bounds(invalid: object) -> None:
    for field in fields(FuchsiaTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_FUCHSIA_TIMING, **{field.name: invalid})


def test_fuchsia_report_requires_every_terminal_gate() -> None:
    report = _report()
    assert report.passed
    invalid = (
        replace(report, records=report.records[:-1]),
        replace(report, battles=report.battles[:-1]),
        replace(report, required_events=(False,) + report.required_events[1:]),
        replace(report, optional_events=(True,) + report.optional_events[1:]),
        replace(report, optional_items_carried=(True,) + report.optional_items_carried[1:]),
        replace(report, flute_retained=False),
        replace(report, snorlax_fight_before=True),
        replace(report, snorlax_fight_after=True),
        replace(report, snorlax_object_tile_crossed=False),
        replace(report, final_bag=report.final_bag[:-1]),
        replace(report, party_hp=(113, 52, 37)),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid)


def test_fuchsia_report_requires_bounded_battle_receipts() -> None:
    report = _report()
    wrong_pp = replace(
        report,
        battles=(replace(report.battles[0], selected_pp_spent=9), *report.battles[1:]),
    )
    wrong_set = replace(
        report,
        battles=(
            *report.battles[:3],
            replace(report.battles[3], trainer_number=15),
            report.battles[4],
        ),
    )
    assert not wrong_pp.passed
    assert not wrong_set.passed


def test_snorlax_receipt_accepts_held_out_damage_roll_spend() -> None:
    report = _report()
    battles = list(report.battles)
    battles[1] = replace(battles[1], selected_pp_spent=8)

    assert replace(report, battles=tuple(battles)).passed


def test_snorlax_policy_falls_back_after_bubblebeam_is_exhausted() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_12,
        player_x=11,
        player_y=62,
        party_count=3,
        battle_state=1,
        first_party_pp=(14, 30, 0, 25),
    )
    assert _snorlax_move_slot(raw) == 1
    assert _snorlax_move_slot(replace(raw, first_party_pp=(14, 30, 1, 25))) == 3


def test_fuchsia_public_report_discloses_assistance_and_optionals() -> None:
    public = _report().public_dict()
    assert public["status"] == "ok"
    assert public["objective"] == "reach_fuchsia"
    assert public["optional_events_false"] == len(OPTIONAL_EVENTS)
    assert public["optional_items_untouched"] == len(OPTIONAL_ITEMS)
    assert public["snorlax"] == {
        "species": 0x84,
        "level": 30,
        "fight_event_before": False,
        "fight_event_after": False,
        "beat_event": True,
        "object_tile_crossed": True,
        "flute_retained": True,
    }


def test_fuchsia_event_addresses_match_pinned_source() -> None:
    assert EventFlag.BEAT_ROUTE_12_TRAINER_0 == 0x482
    assert EventFlag.BEAT_ROUTE_12_TRAINER_3 == 0x485
    assert EventFlag.FIGHT_ROUTE12_SNORLAX == 0x48E
    assert EventFlag.BEAT_ROUTE12_SNORLAX == 0x48F
    assert EventFlag.BEAT_ROUTE_13_TRAINER_0 == 0x491
    assert EventFlag.BEAT_ROUTE_13_TRAINER_1 == 0x492
    assert EventFlag.GOT_EXP_ALL == 0x4B0
