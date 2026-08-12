from __future__ import annotations

from dataclasses import fields, replace

import pytest

import pokemon_red_completion.fuchsia as fuchsia_module
from pokemon_red_completion.actions import MacroAction, MacroActionKind
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
    SnorlaxResourceReport,
    _select_battle_bag_item,
    _snorlax_move_slot,
)
from pokemon_red_completion.observation import EventFlag, ItemId, MapId, RamAddress, RawGameState
from pokemon_red_completion.saffron import JOLTEON
from pokemon_red_completion.tower import TOWER_FINAL_PARTY


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.FUCHSIA_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=4,
        battle_state=0,
        party_species_ids=(0x1C, 0x40, 0x3B, 0x84),
        first_party_level=37,
        first_party_hp=114,
        first_party_max_hp=114,
        first_party_status=0,
        first_party_moves=(0x2C, 0x27, 0x3D, 0x37),
        first_party_pp=(25, 30, 20, 25),
    )


def test_snorlax_funding_sells_only_the_obsolete_cure_shortfall() -> None:
    assert frozenset({0x3D, 0x3A}) == fuchsia_module.SNORLAX_RESOURCE_FISHER_MOVES
    assert fuchsia_module._snorlax_funding_sale_quantities(
        money=18_707,
        potions=3,
        antidotes=3,
        required_cost=19_200,
    ) == (3, 1)
    assert fuchsia_module._snorlax_funding_sale_quantities(
        money=19_200,
        potions=3,
        antidotes=3,
        required_cost=19_200,
    ) == (0, 0)


def test_snorlax_resource_report_adds_the_fifth_member_at_lavender() -> None:
    party_before = (*TOWER_FINAL_PARTY, JOLTEON)
    party_after = (*party_before, fuchsia_module.SNORLAX)
    raw = replace(
        _raw(),
        map_id=MapId.LAVENDER_POKECENTER,
        party_count=5,
        party_species_ids=party_after,
    )
    fisher = FuchsiaBattleEvidence(
        "Route 12 Fisher",
        0xD6,
        0x0E,
        3,
        int(EventFlag.BEAT_ROUTE_12_TRAINER_0),
        fuchsia_module.BUBBLEBEAM,
        1,
    )
    capture = FuchsiaBattleEvidence(
        "Route 12 Snorlax",
        fuchsia_module.SNORLAX,
        None,
        None,
        int(EventFlag.BEAT_ROUTE12_SNORLAX),
        fuchsia_module.BUBBLEBEAM,
        2,
        (fuchsia_module.SNORLAX,),
        30,
        True,
        4,
        1,
        party_before,
        party_after,
    )
    report = SnorlaxResourceReport(
        records=tuple(FuchsiaCheckpoint(str(index), str(index), raw) for index in range(4)),
        battles=(fisher, capture),
        final_raw=raw,
        flute_retained=True,
        fight_event_before=False,
        fight_event_after=False,
        beat_event_after=True,
        final_bag=((int(ItemId.POKE_FLUTE), 1),),
        party_hp=(114, 52, 63, 72, 130),
        party_max_hp=(114, 52, 63, 72, 130),
        party_status=(0, 0, 0, 0, 0),
        frames_executed=1,
        actions_executed=1,
        controller_released=True,
    )

    assert report.passed
    assert report.public_dict()["resource"] == "snorlax_party_member"
    assert not replace(report, beat_event_after=False).passed
    assert not replace(report, controller_released=False).passed


def test_snorlax_funding_sells_early_ball_surplus_but_retains_one() -> None:
    assert fuchsia_module._snorlax_poke_ball_sale_quantity(1) == 0
    assert fuchsia_module._snorlax_poke_ball_sale_quantity(27) == 26
    with pytest.raises(fuchsia_module.FuchsiaChapterError):
        fuchsia_module._snorlax_poke_ball_sale_quantity(0)


def test_snorlax_funding_liquidates_only_tunnel_super_potion_surplus() -> None:
    assert fuchsia_module._snorlax_super_potion_sale_quantity(0) == 0
    assert fuchsia_module._snorlax_super_potion_sale_quantity(2) == 0
    assert fuchsia_module._snorlax_super_potion_sale_quantity(7) == 0
    assert fuchsia_module._snorlax_super_potion_sale_quantity(9) == 2
    with pytest.raises(fuchsia_module.FuchsiaChapterError):
        fuchsia_module._snorlax_super_potion_sale_quantity(-1)


def test_mandatory_fisher_income_covers_observed_capture_reserve_floor() -> None:
    assert (
        fuchsia_module._reverse(fuchsia_module.ROUTE12_FISHER)
        + fuchsia_module._reverse(fuchsia_module.LAVENDER_TO_ROUTE12)
    ) == fuchsia_module.FISHER_TO_LAVENDER
    assert fuchsia_module._snorlax_funding_sale_quantities(
        money=18_447 + 770,
        potions=0,
        antidotes=0,
        required_cost=19_200,
    ) == (0, 0)


def test_battle_bag_selection_can_move_backward_after_a_ball_throw(monkeypatch) -> None:
    assert fuchsia_module.SNORLAX_GREAT_BALL_RESERVE == 32
    assert fuchsia_module.SNORLAX_MIN_GREAT_BALL_RESERVE == 29
    assert fuchsia_module.SNORLAX_TM34_SALE_PROCEEDS == 1_000
    assert fuchsia_module.SNORLAX_POKE_BALL_RESERVE == 1
    assert fuchsia_module.SNORLAX_SUPER_POTION_RESERVE == 7
    assert fuchsia_module.SNORLAX_CAPTURE_POLICY.max_throws == 33
    assert fuchsia_module.SNORLAX_CAPTURE_POLICY.retreat_hp_ratio == 0.65

    class Emulator:
        cursor = 2

        def read_u8(self, address: int) -> int:
            if address == RamAddress.CURRENT_MENU_ITEM:
                return self.cursor
            if address == RamAddress.LIST_SCROLL_OFFSET:
                return 0
            raise AssertionError(f"unexpected read: {address:#06x}")

    class Executor:
        actions: list[MacroAction] = []

        def execute(self, action: MacroAction) -> None:
            self.actions.append(action)
            if action.kind is MacroActionKind.MOVE:
                emulator.cursor += 1 if action.value == "down" else -1

    emulator = Emulator()
    executor = Executor()
    monkeypatch.setattr(
        fuchsia_module,
        "_bag",
        lambda _emulator: {
            ItemId.GREAT_BALL: 1,
            ItemId.SUPER_POTION: 2,
            ItemId.POKE_BALL: 3,
        },
    )

    _select_battle_bag_item(executor, emulator, ItemId.SUPER_POTION)  # type: ignore[arg-type]

    moves = [action for action in executor.actions if action.kind is MacroActionKind.MOVE]
    assert tuple(action.value for action in moves) == ("up",)


def _report() -> FuchsiaChapterReport:
    raw = _raw()
    sets = (3, None, 2, 1, 12)
    opponents = (0xD6, 0x84, 0xDC, 0xDF, 0xCE)
    classes = (0x0E, None, 0x14, 0x17, 0x06)
    events = tuple(int(item) for item in REQUIRED_EVENTS)
    spent = (4, 3, 4, 4, 7)
    initial_bag = ((0x04, 8), (0x28, 1), (0x49, 1), (0xEA, 1))
    final_bag = initial_bag[:-1]
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
                index == 1,
                1 if index == 1 else 0,
                1 if index == 1 else 0,
                (0x1C, 0x40, 0x3B) if index == 1 else (),
                (0x1C, 0x40, 0x3B, 0x84) if index == 1 else (),
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
        initial_bag=initial_bag,
        final_bag=final_bag,
        great_balls_purchased=32,
        funding_super_potions_sold=0,
        funding_potions_sold=0,
        funding_antidotes_sold=0,
        party_hp=(114, 52, 37, 135),
        party_max_hp=(114, 52, 37, 135),
        party_status=(0, 0, 0, 0),
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
    assert fuchsia_module.ROUTE13_BIRD_KEEPER_BITE_PP_BOUND == 15
    assert fuchsia_module.BATTLE_PP_BOUNDS[3] == (1, 15)
    assert fuchsia_module.BATTLE_PP_BOUNDS[4] == (1, 10)


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
        replace(report, great_balls_purchased=28),
        replace(report, final_bag=report.final_bag[:-1]),
        replace(report, party_hp=(113, 52, 37, 135)),
        replace(report, party_status=(0, 0, 0, 0x08)),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid)


def test_fuchsia_report_accepts_bounded_live_capture_budget_and_early_bide_sale() -> None:
    report = _report()
    without_bide = tuple(
        item for item in report.initial_bag if item[0] != int(ItemId.TM34_BIDE)
    )

    assert replace(report, great_balls_purchased=29).passed
    assert replace(report, initial_bag=without_bide).passed


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


def test_snorlax_receipt_accepts_recovery_within_proven_upstream_surplus() -> None:
    report = _report()
    battles = list(report.battles)
    battles[1] = replace(battles[1], recovery_items_used=3)
    initial_bag = (*report.initial_bag, (int(ItemId.SUPER_POTION), 7))

    assert replace(
        report,
        battles=tuple(battles),
        initial_bag=initial_bag,
        funding_super_potions_sold=0,
    ).passed
    battles[1] = replace(battles[1], recovery_items_used=8)
    assert not replace(report, battles=tuple(battles), initial_bag=initial_bag).passed


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
        "captured": True,
        "throws_used": 1,
        "recovery_items_used": 1,
        "great_balls_purchased": 32,
        "funding_super_potions_sold": 0,
        "funding_potions_sold": 0,
        "funding_antidotes_sold": 0,
        "party_before": [0x1C, 0x40, 0x3B],
        "party_after": [0x1C, 0x40, 0x3B, 0x84],
    }


def test_fuchsia_event_addresses_match_pinned_source() -> None:
    assert EventFlag.BEAT_ROUTE_12_TRAINER_0 == 0x482
    assert EventFlag.BEAT_ROUTE_12_TRAINER_3 == 0x485
    assert EventFlag.FIGHT_ROUTE12_SNORLAX == 0x48E
    assert EventFlag.BEAT_ROUTE12_SNORLAX == 0x48F
    assert EventFlag.BEAT_ROUTE_13_TRAINER_0 == 0x491
    assert EventFlag.BEAT_ROUTE_13_TRAINER_1 == 0x492
    assert EventFlag.GOT_EXP_ALL == 0x4B0
