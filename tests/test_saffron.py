from dataclasses import fields, replace

import pytest

import pokemon_red_completion.saffron as saffron
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import Badge, ItemId, MapId, RawGameState
from pokemon_red_completion.saffron import (
    DEFAULT_SAFFRON_TIMING,
    FRESH_WATER_PRICE,
    GUARD_DRINK_FLAG,
    SAFFRON_CHECKPOINT_COUNT,
    THUNDER_STONE_PRICE,
    SaffronChapterReport,
    SaffronCheckpoint,
    SaffronTiming,
)
from pokemon_red_completion.tower import TOWER_FINAL_PARTY

PARTY_BEFORE = (*TOWER_FINAL_PARTY, 0x84)
PARTY_AFTER = (*PARTY_BEFORE, 0x68)


def _terminal() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.SAFFRON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=5,
        battle_state=0,
        badge_bits=int(
            Badge.BOULDER | Badge.CASCADE | Badge.THUNDER | Badge.RAINBOW | Badge.SOUL
        ),
        party_species_ids=PARTY_AFTER,
        first_party_level=42,
        first_party_hp=130,
        first_party_max_hp=130,
        first_party_status=0,
        first_party_moves=(0x82, 0x46, 0x3A, 0x39),
        first_party_pp=(15, 15, 10, 15),
    )


def test_saffron_timing_is_positive_and_bounded() -> None:
    for field in fields(SaffronTiming):
        assert isinstance(getattr(DEFAULT_SAFFRON_TIMING, field.name), int)
        assert getattr(DEFAULT_SAFFRON_TIMING, field.name) > 0
        with pytest.raises(ValueError, match=field.name):
            replace(DEFAULT_SAFFRON_TIMING, **{field.name: 0})


def test_stone_clerk_route_yields_to_fourth_floor_walker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        state = replace(_terminal(), map_id=MapId.CELADON_MART_4F, player_x=4, player_y=2)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        left_attempts = 0

        def execute(self, action: MacroAction) -> MacroAction:
            if action.kind is not MacroActionKind.MOVE:
                return action
            position = (reader.state.player_x, reader.state.player_y)
            if action.value == "right" and position == (4, 2):
                reader.state = replace(reader.state, player_x=5)
            elif action.value == "left" and position == (5, 2):
                reader.state = replace(reader.state, player_x=4)
            elif action.value == "left" and position == (4, 2):
                self.left_attempts += 1
                if self.left_attempts == 3:
                    reader.state = replace(reader.state, player_x=3)
            return action

    executor = Executor()
    monkeypatch.setattr(saffron, "_wait", lambda *args: None)

    saffron._move(
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        ("left",),
        DEFAULT_SAFFRON_TIMING,
        "evolution-stone clerk",
    )

    assert (reader.state.player_x, reader.state.player_y) == (3, 2)
    assert executor.left_attempts == 3


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
        money_before=32_247,
        money_after_stone=32_247 - THUNDER_STONE_PRICE,
        money_after_purchase=32_247 - THUNDER_STONE_PRICE - FRESH_WATER_PRICE,
        money_after=32_247 - THUNDER_STONE_PRICE - FRESH_WATER_PRICE,
        vending_cursor=0,
        fresh_water_before=0,
        fresh_water_after_purchase=1,
        fresh_water_after_guard=0,
        guard_flag_before=0,
        guard_flag_after_consumption=0,
        guard_flag_after_dialogue=GUARD_DRINK_FLAG,
        bag_before=bag,
        bag_after=bag,
        party_before=PARTY_BEFORE,
        party_after=PARTY_AFTER,
        party_hp=(130, 47, 40, 120, 65),
        party_max_hp=(130, 47, 40, 120, 65),
        party_status=(0, 0, 0, 0, 0),
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


def test_saffron_report_accepts_level_43_healed_lineage() -> None:
    raw = replace(
        _terminal(),
        first_party_level=43,
        first_party_hp=133,
        first_party_max_hp=133,
    )
    bag = ((int(ItemId.TM21_MEGA_DRAIN), 1),)
    report = SaffronChapterReport(
        records=tuple(
            SaffronCheckpoint(str(index), str(index), raw)
            for index in range(SAFFRON_CHECKPOINT_COUNT)
        ),
        final_raw=raw,
        money_before=32_247,
        money_after_stone=32_247 - THUNDER_STONE_PRICE,
        money_after_purchase=32_247 - THUNDER_STONE_PRICE - FRESH_WATER_PRICE,
        money_after=32_247 - THUNDER_STONE_PRICE - FRESH_WATER_PRICE,
        vending_cursor=0,
        fresh_water_before=0,
        fresh_water_after_purchase=1,
        fresh_water_after_guard=0,
        guard_flag_before=0,
        guard_flag_after_consumption=0,
        guard_flag_after_dialogue=GUARD_DRINK_FLAG,
        bag_before=bag,
        bag_after=bag,
        party_before=PARTY_BEFORE,
        party_after=PARTY_AFTER,
        party_hp=(133, 47, 40, 120, 65),
        party_max_hp=(133, 47, 40, 120, 65),
        party_status=(0, 0, 0, 0, 0),
        battle_free=True,
        frames_executed=1,
        actions_executed=1,
        controller_released=True,
    )

    assert report.passed


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
        money_before=32_247,
        money_after_stone=32_247 - THUNDER_STONE_PRICE,
        money_after_purchase=32_247 - THUNDER_STONE_PRICE - FRESH_WATER_PRICE,
        money_after=32_247 - THUNDER_STONE_PRICE - FRESH_WATER_PRICE,
        vending_cursor=0,
        fresh_water_before=0,
        fresh_water_after_purchase=1,
        fresh_water_after_guard=0,
        guard_flag_before=0,
        guard_flag_after_consumption=0,
        guard_flag_after_dialogue=GUARD_DRINK_FLAG,
        bag_before=bag,
        bag_after=bag,
        party_before=PARTY_BEFORE,
        party_after=PARTY_AFTER,
        party_hp=(130, 47, 40, 120, 65),
        party_max_hp=(130, 47, 40, 120, 65),
        party_status=(0, 0, 0, 0, 0),
        battle_free=True,
        frames_executed=1,
        actions_executed=1,
        controller_released=True,
    )

    assert not replace(report, **{field_name: value}).passed
