from dataclasses import fields, replace

import pytest

from pokemon_red_completion.observation import Badge, ItemId, MapId, RawGameState
from pokemon_red_completion.saffron import (
    DEFAULT_SAFFRON_TIMING,
    FRESH_WATER_PRICE,
    GUARD_DRINK_FLAG,
    SAFFRON_CHECKPOINT_COUNT,
    SaffronChapterReport,
    SaffronCheckpoint,
    SaffronTiming,
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
        badge_bits=int(
            Badge.BOULDER | Badge.CASCADE | Badge.THUNDER | Badge.RAINBOW | Badge.SOUL
        ),
        party_species_ids=TOWER_FINAL_PARTY,
        first_party_level=42,
        first_party_hp=130,
        first_party_max_hp=130,
        first_party_status=0,
        first_party_moves=(0x82, 0x46, 0x3D, 0x39),
        first_party_pp=(15, 15, 20, 15),
    )


def test_saffron_timing_is_positive_and_bounded() -> None:
    for field in fields(SaffronTiming):
        assert isinstance(getattr(DEFAULT_SAFFRON_TIMING, field.name), int)
        assert getattr(DEFAULT_SAFFRON_TIMING, field.name) > 0
        with pytest.raises(ValueError, match=field.name):
            replace(DEFAULT_SAFFRON_TIMING, **{field.name: 0})


def test_saffron_report_proves_purchase_handoff_order_and_terminal() -> None:
    raw = _terminal()
    bag = (
        (int(ItemId.POKE_BALL), 8),
        (int(ItemId.TM21_MEGA_DRAIN), 1),
    )
    report = SaffronChapterReport(
        records=tuple(
            SaffronCheckpoint(str(index), str(index), raw)
            for index in range(SAFFRON_CHECKPOINT_COUNT)
        ),
        final_raw=raw,
        money_before=41_545,
        money_after_purchase=41_545 - FRESH_WATER_PRICE,
        money_after=41_345,
        vending_cursor=0,
        fresh_water_before=0,
        fresh_water_after_purchase=1,
        fresh_water_after_guard=0,
        guard_flag_before=0,
        guard_flag_after_consumption=0,
        guard_flag_after_dialogue=GUARD_DRINK_FLAG,
        bag_before=bag,
        bag_after=bag,
        party_hp=(130, 52, 37),
        party_max_hp=(130, 52, 37),
        party_status=(0, 0, 0),
        battle_free=True,
        frames_executed=1,
        actions_executed=1,
        controller_released=True,
    )

    assert report.passed
    assert report.public_dict()["guard_handoff"] == {
        "fresh_water": [0, 1, 0],
        "flag_before": 0,
        "flag_after_consumption": 0,
        "flag_after_dialogue": GUARD_DRINK_FLAG,
        "consumed_before_global_access": True,
    }


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("vending_cursor", 1),
        ("fresh_water_after_guard", 1),
        ("guard_flag_after_consumption", GUARD_DRINK_FLAG),
        ("guard_flag_after_dialogue", 0),
        ("battle_free", False),
    ),
)
def test_saffron_report_rejects_missing_evidence(field_name: str, value: object) -> None:
    raw = _terminal()
    bag = ((int(ItemId.TM21_MEGA_DRAIN), 1),)
    report = SaffronChapterReport(
        records=tuple(
            SaffronCheckpoint(str(index), str(index), raw)
            for index in range(SAFFRON_CHECKPOINT_COUNT)
        ),
        final_raw=raw,
        money_before=41_545,
        money_after_purchase=41_345,
        money_after=41_345,
        vending_cursor=0,
        fresh_water_before=0,
        fresh_water_after_purchase=1,
        fresh_water_after_guard=0,
        guard_flag_before=0,
        guard_flag_after_consumption=0,
        guard_flag_after_dialogue=GUARD_DRINK_FLAG,
        bag_before=bag,
        bag_after=bag,
        party_hp=(130, 52, 37),
        party_max_hp=(130, 52, 37),
        party_status=(0, 0, 0),
        battle_free=True,
        frames_executed=1,
        actions_executed=1,
        controller_released=True,
    )

    assert not replace(report, **{field_name: value}).passed
