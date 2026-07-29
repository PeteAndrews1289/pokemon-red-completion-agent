from dataclasses import fields, replace

import pytest

from pokemon_red_completion.observation import Badge, EventFlag, MapId, RawGameState
from pokemon_red_completion.silph import (
    DEFAULT_SILPH_TIMING,
    SILPH_CHECKPOINT_COUNT,
    THIRD_FLOOR_GUARD,
    SilphChapterReport,
    SilphCheckpoint,
    SilphTiming,
)
from pokemon_red_completion.tower import TOWER_FINAL_PARTY


def _terminal() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.SAFFRON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=3,
        battle_state=0,
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER | Badge.RAINBOW | Badge.SOUL),
        party_species_ids=TOWER_FINAL_PARTY,
        first_party_level=45,
        first_party_hp=139,
        first_party_max_hp=139,
        first_party_status=0,
        first_party_moves=(0x82, 0x46, 0x3A, 0x39),
        first_party_pp=(15, 15, 10, 15),
    )


def _report() -> SilphChapterReport:
    raw = _terminal()
    events = (
        EventFlag.BEAT_SILPH_CO_5F_TRAINER_0,
        EventFlag.BEAT_SILPH_CO_3F_TRAINER_0,
        EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2,
        EventFlag.BEAT_SILPH_CO_RIVAL,
        EventFlag.BEAT_SILPH_CO_11F_TRAINER_0,
        EventFlag.SILPH_CO_11_UNLOCKED_DOOR,
        EventFlag.BEAT_SILPH_CO_GIOVANNI,
        EventFlag.GOT_MASTER_BALL,
    )
    return SilphChapterReport(
        records=tuple(
            SilphCheckpoint(str(index), str(index), raw) for index in range(SILPH_CHECKPOINT_COUNT)
        ),
        final_raw=raw,
        money_before=41_345,
        money_after=40_894,
        tm13_event=True,
        tm13_transfer_before_event=True,
        other_roof_rewards_untouched=True,
        fresh_water_after_reward=0,
        tm13_after_teaching=0,
        upgraded_moves=(0x82, 0x46, 0x3A, 0x39),
        upgraded_pp=(15, 15, 10, 15),
        rival_potions_used=0,
        hyper_potions_remaining=6,
        max_repel_remaining=0,
        card_key_quantity=1,
        master_ball_quantity=1,
        required_events=tuple((int(event), True) for event in events),
        lapras_flag_before=0x0E,
        lapras_flag_after=0x0E,
        party_hp=(139, 52, 37),
        party_max_hp=(139, 52, 37),
        party_status=(0, 0, 0),
        controller_released=True,
        frames_executed=1,
        actions_executed=1,
    )


def test_silph_timing_is_positive_and_bounded() -> None:
    for field in fields(SilphTiming):
        assert getattr(DEFAULT_SILPH_TIMING, field.name) > 0
        with pytest.raises(ValueError, match=field.name):
            replace(DEFAULT_SILPH_TIMING, **{field.name: 0})


def test_silph_report_proves_required_story_and_terminal() -> None:
    report = _report()
    assert report.passed
    assert report.public_dict()["supply"] == {
        "hyper_potions_bought": 6,
        "used_by_rival_policy": 0,
        "remaining": 6,
        "max_repel_bought": 1,
        "max_repel_remaining": 0,
    }
    assert THIRD_FLOOR_GUARD == (
        "down",
        "down",
        "down",
        "down",
        "down",
        "left",
        "left",
        "down",
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("rival_potions_used", 2),
        ("hyper_potions_remaining", 4),
        ("max_repel_remaining", 1),
        ("tm13_event", False),
        ("tm13_transfer_before_event", False),
        ("other_roof_rewards_untouched", False),
        ("fresh_water_after_reward", 1),
        ("tm13_after_teaching", 1),
        ("card_key_quantity", 0),
        ("master_ball_quantity", 0),
        ("lapras_flag_after", 0x0F),
        ("controller_released", False),
    ),
)
def test_silph_report_rejects_missing_evidence(
    field_name: str,
    value: object,
) -> None:
    assert not replace(_report(), **{field_name: value}).passed
