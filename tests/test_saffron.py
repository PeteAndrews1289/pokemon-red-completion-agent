from dataclasses import fields, replace

import pytest

import pokemon_red_completion.saffron as saffron
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import Badge, ItemId, MapId, RawGameState
from pokemon_red_completion.saffron import (
    DEFAULT_SAFFRON_TIMING,
    FRESH_WATER_PRICE,
    GUARD_DRINK_FLAG,
    SAFFRON_ACCESS_CHECKPOINT_COUNT,
    SAFFRON_CHECKPOINT_COUNT,
    THUNDER_STONE_PRICE,
    SaffronAccessChapterReport,
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
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER | Badge.RAINBOW | Badge.SOUL),
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
        return_attempts = 0

        def execute(self, action: MacroAction) -> MacroAction:
            if action.kind is not MacroActionKind.MOVE:
                return action
            position = (reader.state.player_x, reader.state.player_y)
            if action.value == "right" and position == (4, 2):
                reader.state = replace(reader.state, player_x=5)
            elif action.value == "left" and position == (5, 2):
                self.return_attempts += 1
                if self.return_attempts >= 3:
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
    assert executor.return_attempts == 4


def test_stone_clerk_route_yields_at_west_fourth_floor_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        state = replace(_terminal(), map_id=MapId.CELADON_MART_4F, player_x=2, player_y=2)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        left_attempts = 0

        def execute(self, action: MacroAction) -> MacroAction:
            if action.kind is not MacroActionKind.MOVE:
                return action
            position = (reader.state.player_x, reader.state.player_y)
            if action.value == "right" and position == (2, 2):
                reader.state = replace(reader.state, player_x=3)
            elif action.value == "left" and position == (3, 2):
                reader.state = replace(reader.state, player_x=2)
            elif action.value == "left" and position == (2, 2):
                self.left_attempts += 1
                if self.left_attempts == 2:
                    reader.state = replace(reader.state, player_x=1)
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

    assert (reader.state.player_x, reader.state.player_y) == (1, 2)
    assert executor.left_attempts == 2


def test_mart_roof_route_yields_to_fifth_floor_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        state = replace(_terminal(), map_id=MapId.CELADON_MART_5F, player_x=15, player_y=2)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        left_attempts = 0
        return_attempts = 0
        yielded = False

        def execute(self, action: MacroAction) -> MacroAction:
            if action.kind is not MacroActionKind.MOVE:
                return action
            position = (reader.state.player_x, reader.state.player_y)
            if action.value == "down" and position == (15, 2):
                reader.state = replace(reader.state, player_y=3)
                self.yielded = True
            elif action.value == "up" and position == (15, 3):
                self.return_attempts += 1
                if self.return_attempts >= 2:
                    reader.state = replace(reader.state, player_y=2)
            elif action.value == "left" and position == (15, 2) and self.yielded:
                self.left_attempts += 1
                if self.left_attempts >= 2:
                    reader.state = replace(reader.state, player_x=14)
            return action

    executor = Executor()
    monkeypatch.setattr(saffron, "_wait", lambda *args: None)

    saffron._move(
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        ("left",),
        DEFAULT_SAFFRON_TIMING,
        "mart_roof",
    )

    assert (reader.state.player_x, reader.state.player_y) == (14, 2)
    assert executor.return_attempts == 3
    assert executor.left_attempts == 2


def test_stone_clerk_return_retreats_until_fourth_floor_walker_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        state = replace(_terminal(), map_id=MapId.CELADON_MART_4F, player_x=5, player_y=2)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        retreated = False
        yielded = False

        def execute(self, action: MacroAction) -> MacroAction:
            if action.kind is not MacroActionKind.MOVE:
                return action
            x = reader.state.player_x or 0
            if action.value == "left":
                reader.state = replace(reader.state, player_x=x - 1)
                if x - 1 == 1:
                    self.retreated = True
            elif action.value == "down" and x == 1:
                reader.state = replace(reader.state, player_y=3)
                self.yielded = True
            elif action.value == "up" and reader.state.player_y == 3:
                reader.state = replace(reader.state, player_y=2)
            elif action.value == "right" and (self.yielded or x != 5):
                reader.state = replace(reader.state, player_x=x + 1)
            return action

    executor = Executor()

    class Emulator:
        def read_u8(self, address: int) -> int:
            return 11 if address == saffron.STONE_CLERK_WALKER_X else 6

    monkeypatch.setattr(saffron, "_wait", lambda *args: None)

    saffron._move(
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        Emulator(),  # type: ignore[arg-type]
        ("right",),
        DEFAULT_SAFFRON_TIMING,
        "fourth-floor stair return",
    )

    assert (reader.state.player_x, reader.state.player_y) == (6, 2)
    assert executor.retreated
    assert executor.yielded


def test_stone_clerk_return_recovers_a_later_corridor_deadlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        state = replace(_terminal(), map_id=MapId.CELADON_MART_4F, player_x=9, player_y=2)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Executor:
        retreated = False
        yielded = False

        def execute(self, action: MacroAction) -> MacroAction:
            if action.kind is not MacroActionKind.MOVE:
                return action
            x = reader.state.player_x or 0
            if action.value == "left":
                reader.state = replace(reader.state, player_x=x - 1)
                if x - 1 == 1:
                    self.retreated = True
            elif action.value == "down" and x == 1:
                reader.state = replace(reader.state, player_y=3)
                self.yielded = True
            elif action.value == "up" and reader.state.player_y == 3:
                reader.state = replace(reader.state, player_y=2)
            elif action.value == "right" and (self.yielded or x != 9):
                reader.state = replace(reader.state, player_x=x + 1)
            return action

    executor = Executor()

    class Emulator:
        def read_u8(self, address: int) -> int:
            # The walker only needs to clear the x=1 alcove entrance. It does
            # not need to move beyond this late x=10 corridor destination.
            return 9 if address == saffron.STONE_CLERK_WALKER_X else 6

    monkeypatch.setattr(saffron, "_wait", lambda *args: None)

    saffron._move(
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        Emulator(),  # type: ignore[arg-type]
        ("right",),
        DEFAULT_SAFFRON_TIMING,
        "fourth-floor stair return",
    )

    assert (reader.state.player_x, reader.state.player_y) == (10, 2)
    assert executor.retreated
    assert executor.yielded


def test_mart_2f_return_observes_customer_before_crossing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        state = replace(_terminal(), map_id=MapId.CELADON_MART_2F, player_x=15, player_y=2)

        def read(self) -> RawGameState:
            return self.state

    reader = Reader()

    class Emulator:
        frame_count = 0
        pressed_buttons = frozenset()
        observations = 0

        def read_u8(self, address: int) -> int:
            if address == saffron.MART_2F_GIRL_X:
                self.observations += 1
                return 18 if self.observations < 4 else 17
            if address == saffron.MART_2F_GIRL_Y:
                return 6
            raise AssertionError(address)

    class Executor:
        waits = 0
        left_attempts = 0

        def execute(self, action: MacroAction) -> MacroAction:
            if action.kind is MacroActionKind.WAIT:
                self.waits += 1
            elif action.kind is MacroActionKind.MOVE and action.value == "left":
                self.left_attempts += 1
                if emulator.observations >= 4:
                    reader.state = replace(reader.state, player_x=14)
            return action

    executor = Executor()
    emulator = Emulator()
    monkeypatch.setattr(saffron, "_wait", lambda *args: None)

    saffron._move(
        executor,  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        emulator,  # type: ignore[arg-type]
        ("left",),
        DEFAULT_SAFFRON_TIMING,
        "mart_1f_return",
    )

    assert (reader.state.player_x, reader.state.player_y) == (14, 2)
    assert executor.waits == 3
    assert executor.left_attempts == 2


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


def test_saffron_access_report_accepts_pre_erika_party_and_preserves_it() -> None:
    party = TOWER_FINAL_PARTY
    moves = (0x2C, 0x27, 0x3D, 0x37)
    pp = (25, 30, 20, 25)
    raw = replace(
        _terminal(),
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER),
        party_count=len(party),
        party_species_ids=party,
        first_party_level=36,
        first_party_hp=98,
        first_party_max_hp=98,
        first_party_moves=moves,
        first_party_pp=pp,
    )
    bag = ((int(ItemId.POKE_BALL), 8),)
    report = SaffronAccessChapterReport(
        records=tuple(
            SaffronCheckpoint(str(index), str(index), raw)
            for index in range(SAFFRON_ACCESS_CHECKPOINT_COUNT)
        ),
        final_raw=raw,
        money_before=11_852,
        money_after_purchase=11_852 - FRESH_WATER_PRICE,
        money_after=11_852 - FRESH_WATER_PRICE,
        vending_cursor=0,
        fresh_water_before=0,
        fresh_water_after_purchase=1,
        fresh_water_after_guard=0,
        guard_flag_before=0,
        guard_flag_after_consumption=0,
        guard_flag_after_dialogue=GUARD_DRINK_FLAG,
        bag_before=bag,
        bag_after=bag,
        party_before=party,
        party_after=party,
        lead_level_before=36,
        lead_moves_before=moves,
        lead_pp_before=pp,
        party_hp=(98, 53, 37),
        party_max_hp=(98, 53, 37),
        party_status=(0, 0, 0),
        battle_free=True,
        frames_executed=1,
        actions_executed=1,
        controller_released=True,
    )

    assert report.passed
    assert report.public_dict()["optional_party_construction"] is False
    assert not replace(report, party_after=(*party, 0x68)).passed
    assert not replace(report, final_raw=replace(raw, first_party_level=37)).passed


def test_saffron_report_accepts_level_44_healed_lineage() -> None:
    raw = replace(
        _terminal(),
        first_party_level=44,
        first_party_hp=137,
        first_party_max_hp=137,
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
        party_hp=(137, 47, 40, 120, 65),
        party_max_hp=(137, 47, 40, 120, 65),
        party_status=(0, 0, 0, 0, 0),
        battle_free=True,
        frames_executed=1,
        actions_executed=1,
        controller_released=True,
    )

    assert report.passed
    assert not replace(report, final_raw=replace(raw, first_party_level=45)).passed


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
