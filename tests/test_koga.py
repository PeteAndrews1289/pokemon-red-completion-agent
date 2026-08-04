from __future__ import annotations

from dataclasses import fields, replace

import pytest

import pokemon_red_completion.koga as koga_module
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.koga import (
    CENTER_TO_GYM,
    DEFAULT_KOGA_TIMING,
    GYM_TO_JUGGLER3,
    JUGGLER3_TO_TAMER2,
    JUGGLER_4_PIVOT_HP_THRESHOLD,
    KOGA_CHECKPOINT_COUNT,
    KOGA_OPPONENT,
    KOGA_TRAINER_CLASS,
    KOGA_TRAINER_NUMBER,
    MANDATORY_TRAINER_EVENTS,
    MUK_SPECIES_ID,
    OPTIONAL_TRAINER_EVENTS,
    REGULAR_TRAINER_EVENTS,
    KogaBattleEvidence,
    KogaChapterError,
    KogaChapterReport,
    KogaCheckpoint,
    KogaTiming,
    _koga_fainted_pivot_target,
    _koga_matchup_pivot_target,
    _koga_move_slot,
    _koga_reserve_pivot_target,
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
            battles=(replace(report.battles[0], selected_pp_spent=16), *report.battles[1:]),
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


def test_koga_report_records_a_living_party_continuation() -> None:
    report = _report()
    continued_battle = replace(
        report.battles[-1],
        hp_after=0,
        continued_after_faint=True,
    )
    continued = replace(report, battles=(*report.battles[:-1], continued_battle))

    assert continued.passed
    assert continued.public_dict()["koga"]["continued_after_faint"] is True

    reserve_fainted = replace(
        report.battles[-1],
        hp_after=14,
        continued_after_faint=True,
    )
    continued_from_reserve = replace(
        report,
        battles=(*report.battles[:-1], reserve_fainted),
    )
    assert continued_from_reserve.passed


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
    assert _nurse_approach_directions(replace(nurse, map_id=MapId.FUCHSIA_CITY, player_y=4)) == ()


def test_koga_disable_fallback_uses_a_legal_ranked_reserve_attack() -> None:
    raw = replace(_raw(), player_disabled_move_slot=4)

    assert _koga_move_slot(raw, allow_disable_fallback=True) == 3
    with pytest.raises(KogaChapterError, match="no legal ranked attack"):
        _koga_move_slot(raw, allow_disable_fallback=False)


def test_koga_low_hp_lead_pivots_to_the_healthiest_reserve() -> None:
    raw = replace(
        _raw(),
        battle_state=2,
        active_party_index=0,
        active_party_hp=40,
        active_party_max_hp=120,
    )

    assert JUGGLER_4_PIVOT_HP_THRESHOLD == 50
    assert _koga_reserve_pivot_target(raw, (40, 75, 130, 90), 50) == 2
    assert _koga_reserve_pivot_target(raw, (40, 45, 0), 50) is None
    assert _koga_reserve_pivot_target(replace(raw, active_party_index=2), (40, 75, 130), 50) is None


def test_koga_hands_muk_to_the_healthiest_living_reserve_before_attacking() -> None:
    muk = replace(
        _raw(),
        battle_state=2,
        enemy_species_id=MUK_SPECIES_ID,
        active_party_index=0,
        active_party_hp=126,
    )

    assert _koga_matchup_pivot_target(muk, (126, 75, 130, 143), MUK_SPECIES_ID) == 3
    assert _koga_matchup_pivot_target(muk, (126, 75, 130, 0), MUK_SPECIES_ID) == 2
    assert _koga_matchup_pivot_target(
        replace(muk, active_party_index=3),
        (126, 75, 130, 143),
        MUK_SPECIES_ID,
    ) is None
    assert _koga_matchup_pivot_target(muk, (126, 75, 130, 143), None) is None


def test_koga_fainted_member_continues_with_the_healthiest_living_teammate() -> None:
    fainted = replace(
        _raw(),
        battle_state=2,
        active_party_index=0,
        active_party_hp=0,
    )

    assert _koga_fainted_pivot_target(fainted, (0, 75, 130, 90)) == 2
    assert _koga_fainted_pivot_target(
        replace(fainted, active_party_index=None),
        (0, 75, 130, 90),
    ) == 2
    assert _koga_fainted_pivot_target(
        replace(fainted, active_party_index=None, active_party_hp=None),
        (126, 75, 130, 0),
        last_active_party_index=0,
    ) == 2
    assert _koga_fainted_pivot_target(fainted, (0, 75, 0, 90)) == 3
    assert _koga_fainted_pivot_target(fainted, (0, 0, 0)) is None
    assert _koga_fainted_pivot_target(
        replace(fainted, active_party_hp=1),
        (1, 75, 130),
    ) is None


def test_koga_fainted_continuation_waits_for_stable_party_hp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Runtime:
        def __init__(self) -> None:
            self.actions: list[object] = []

        def execute(self, action: object) -> None:
            self.actions.append(action)

        def read(self) -> RawGameState:
            return replace(
                _raw(),
                battle_state=2,
                active_party_index=None,
                active_party_hp=None,
            )

    runtime = Runtime()
    party_reads = iter(((), (126, 75, 130, 0)))
    monkeypatch.setattr(koga_module, "_party_hp", lambda _emulator: next(party_reads))

    assert koga_module._settle_koga_fainted_pivot_target(
        runtime,  # type: ignore[arg-type]
        runtime,  # type: ignore[arg-type]
        runtime,  # type: ignore[arg-type]
        KogaTiming(wait_frames=1),
        last_active_party_index=0,
    ) == 2
    assert getattr(runtime.actions[0], "kind", None) is MacroActionKind.CONFIRM


def test_koga_pivoted_reserve_uses_its_own_legal_move() -> None:
    raw = replace(
        _raw(),
        active_party_index=3,
        active_party_moves=(0x1D, 0x85, 0x9C, 0),
        active_party_pp=(15, 20, 10, 0),
    )

    assert _koga_move_slot(raw, allow_disable_fallback=True) == 1


def test_koga_source_addresses_and_ids_are_pinned() -> None:
    assert RamAddress.OBTAINED_BADGES == 0xD356
    assert RamAddress.BEAT_GYM_FLAGS == 0xD72A
    assert EventFlag.GOT_TM06 == 0x258
    assert EventFlag.BEAT_KOGA == 0x259
    assert tuple(int(event) for event in REGULAR_TRAINER_EVENTS) == tuple(range(0x25A, 0x260))
    assert ItemId.TM06_TOXIC == 0xCE
    assert MapId.FUCHSIA_GYM == 0x9D
    assert Badge.SOUL == 0x10
