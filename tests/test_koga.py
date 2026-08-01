from __future__ import annotations

from dataclasses import fields, replace

import pytest

from pokemon_red_completion.koga import (
    CENTER_TO_GYM,
    DEFAULT_KOGA_TIMING,
    GYM_TO_JUGGLER3,
    JUGGLER3_TO_TAMER2,
    KOGA_CHECKPOINT_COUNT,
    KOGA_OPPONENT,
    KOGA_TRAINER_CLASS,
    KOGA_TRAINER_NUMBER,
    MANDATORY_TRAINER_EVENTS,
    OPTIONAL_TRAINER_EVENTS,
    REGULAR_TRAINER_EVENTS,
    KogaBattleEvidence,
    KogaChapterError,
    KogaChapterReport,
    KogaCheckpoint,
    KogaTiming,
    _koga_move_slot,
    _nurse_approach_directions,
)
from pokemon_red_completion.observation import (
    Badge,
    EventFlag,
    ItemId,
    MapId,
    RamAddress,
    RawGameState,
)


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.FUCHSIA_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=3,
        battle_state=0,
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER | Badge.SOUL),
        party_species_ids=(0x1C, 0x40, 0x3B),
        first_party_level=40,
        first_party_hp=124,
        first_party_max_hp=124,
        first_party_status=0,
        first_party_moves=(0x82, 0x27, 0x3D, 0x39),
        first_party_pp=(25, 30, 20, 15),
    )


def _report() -> KogaChapterReport:
    raw = _raw()
    initial_bag = (
        (0x04, 8),
        (int(ItemId.GOLD_TEETH), 1),
        (0x49, 1),
        (int(ItemId.HM03_SURF), 1),
    )
    battles = (
        KogaBattleEvidence("Juggler 3", 0xDD, 0x15, 3, 0x25B, 5, 84, 117, 0),
        KogaBattleEvidence("Tamer 2", 0xDE, 0x16, 2, 0x25E, 5, 66, 120, 0x40),
        KogaBattleEvidence("Juggler 4", 0xDD, 0x15, 4, 0x25F, 5, 102, 120, 0),
        KogaBattleEvidence(
            "Koga",
            KOGA_OPPONENT,
            KOGA_TRAINER_CLASS,
            KOGA_TRAINER_NUMBER,
            int(EventFlag.BEAT_KOGA),
            9,
            107,
            124,
            0,
        ),
    )
    return KogaChapterReport(
        records=tuple(
            KogaCheckpoint(f"gate_{index}", f"Gate {index}", raw)
            for index in range(KOGA_CHECKPOINT_COUNT)
        ),
        battles=battles,
        final_raw=raw,
        initial_bag=initial_bag,
        final_bag=tuple(sorted((*initial_bag, (int(ItemId.TM06_TOXIC), 1)))),
        initial_money=20_339,
        final_money=28_191,
        trainer_events_before_koga=(False, True, False, False, True, True),
        trainer_events_after_koga=(True,) * 6,
        got_tm06=True,
        beat_koga=True,
        soul_badge=True,
        soul_badge_mirror=True,
        party_hp=(124, 47, 40),
        party_max_hp=(124, 47, 40),
        party_status=(0, 0, 0),
        surf_pp=15,
        frames_executed=120_000,
        actions_executed=900,
        controller_released=True,
    )


def test_koga_timing_is_positive_and_bounded() -> None:
    assert KogaTiming() == DEFAULT_KOGA_TIMING
    assert all(
        isinstance(getattr(DEFAULT_KOGA_TIMING, field.name), int)
        and getattr(DEFAULT_KOGA_TIMING, field.name) > 0
        for field in fields(KogaTiming)
    )


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_koga_timing_rejects_invalid_bounds(invalid: object) -> None:
    for field in fields(KogaTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_KOGA_TIMING, **{field.name: invalid})


def test_koga_report_requires_every_terminal_gate() -> None:
    report = _report()
    assert report.passed
    invalid = (
        replace(report, records=report.records[:-1]),
        replace(report, battles=report.battles[:-1]),
        replace(
            report,
            battles=(replace(report.battles[0], hp_after=0), *report.battles[1:]),
        ),
        replace(
            report,
            battles=(replace(report.battles[0], selected_pp_spent=9), *report.battles[1:]),
        ),
        replace(report, trainer_events_before_koga=(True,) * 6),
        replace(report, trainer_events_after_koga=(True,) * 5 + (False,)),
        replace(report, got_tm06=False),
        replace(report, beat_koga=False),
        replace(report, soul_badge=False),
        replace(report, soul_badge_mirror=False),
        replace(report, party_hp=(123, 47, 40)),
        replace(report, final_money=33_388),
        replace(report, surf_pp=14),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid)


def test_koga_public_report_is_honest_about_geography_and_minimum_trainers() -> None:
    public = _report().public_dict()
    assert public["status"] == "ok"
    assert public["objective"] == "defeat_koga"
    assert public["geographic_dependency"] == {
        "reason": "post-Surf Fuchsia cannot legally return to Celadon before Soul Badge",
        "route15_return": "one_way_blocked",
        "cycling_road": "bicycle_required",
        "surf": "soul_badge_required",
        "unblocks": "Surf route toward the western Kanto network",
    }
    assert [item["trainer_number"] for item in public["mandatory_trainers"]] == [3, 2, 4]
    assert public["recoveries"] == {
        "pokemon_center_visits_before_koga": 2,
        "mart_purchases": 0,
        "consumables_used": 0,
    }
    assert public["koga"]["surf_pp_spent"] == 9
    assert public["koga"]["terminal_mutual_ko"] is False
    assert public["koga"]["party_restored_at_boundary"] is True
    assert public["rewards"]["regular_trainers_deactivated"] is True


def test_koga_report_records_a_recovered_terminal_mutual_ko() -> None:
    report = _report()
    recovered_battle = replace(
        report.battles[-1],
        hp_after=0,
        terminal_mutual_ko=True,
    )
    recovered = replace(report, battles=(*report.battles[:-1], recovered_battle))

    assert recovered.passed
    assert recovered.public_dict()["koga"]["terminal_mutual_ko"] is True


def test_koga_routes_and_minimum_trainer_set_are_pinned() -> None:
    assert (
        *("down",) * 5,
        *("left",) * 14,
        "up",
    ) == CENTER_TO_GYM
    assert (
        "up",
        *("right",) * 5,
        *("up",) * 7,
        "left",
        "up",
    ) == GYM_TO_JUGGLER3
    assert JUGGLER3_TO_TAMER2 == ("up",) * 4
    assert len(REGULAR_TRAINER_EVENTS) == 6
    assert MANDATORY_TRAINER_EVENTS == (
        EventFlag.BEAT_FUCHSIA_GYM_TRAINER_1,
        EventFlag.BEAT_FUCHSIA_GYM_TRAINER_4,
        EventFlag.BEAT_FUCHSIA_GYM_TRAINER_5,
    )
    assert len(OPTIONAL_TRAINER_EVENTS) == 3


def test_koga_nurse_approach_normalizes_the_adjacent_ready_tile() -> None:
    nurse = _raw()
    assert _nurse_approach_directions(nurse) == ()
    assert _nurse_approach_directions(replace(nurse, player_y=4)) == ("up",)
    assert _nurse_approach_directions(replace(nurse, player_x=2, player_y=4)) == ()
    assert (
        _nurse_approach_directions(
            replace(nurse, map_id=MapId.FUCHSIA_CITY, player_y=4)
        )
        == ()
    )


def test_koga_disable_fallback_uses_a_legal_ranked_reserve_attack() -> None:
    raw = replace(_raw(), player_disabled_move_slot=4)

    assert _koga_move_slot(raw, allow_disable_fallback=True) == 3
    with pytest.raises(KogaChapterError, match="no legal ranked attack"):
        _koga_move_slot(raw, allow_disable_fallback=False)


def test_koga_source_addresses_and_ids_are_pinned() -> None:
    assert RamAddress.OBTAINED_BADGES == 0xD356
    assert RamAddress.BEAT_GYM_FLAGS == 0xD72A
    assert EventFlag.GOT_TM06 == 0x258
    assert EventFlag.BEAT_KOGA == 0x259
    assert tuple(int(event) for event in REGULAR_TRAINER_EVENTS) == tuple(
        range(0x25A, 0x260)
    )
    assert ItemId.TM06_TOXIC == 0xCE
    assert MapId.FUCHSIA_GYM == 0x9D
    assert Badge.SOUL == 0x10
