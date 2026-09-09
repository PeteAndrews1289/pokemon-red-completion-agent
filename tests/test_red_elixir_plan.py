"""Literal cartridge-effect expectations for the pure one-Elixir contract."""

from dataclasses import FrozenInstanceError, replace

import pytest

from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_elixir_plan import (
    RedElixirPlanError,
    plan_field_elixir,
    verify_field_elixir,
)


def state():
    return RawGameState(
        game_started=True, map_id=113, player_x=6, player_y=2, party_count=2,
        battle_state=0, badge_bits=255, event_flags=bytes(319), player_money=1234,
        bag_items=((53, 3), (82, 1), (4, 2)), bag_item_ids=(53, 82, 4),
        party_species_ids=(104, 28), party_levels=(56, 67),
        party_hp=(118, 164), party_max_hp=(172, 217), party_status=(0, 0),
        party_moves=((87, 33, 0, 0), (57, 58, 0, 0)),
        party_pp=((1, 35, 0, 0), (2, 6, 0, 0)),
        first_party_level=56, first_party_hp=118, first_party_max_hp=172,
        first_party_status=0, first_party_moves=(87, 33, 0, 0), first_party_pp=(1, 35, 0, 0),
        status_flags_1=0, repel_remaining_steps=0,
    )


def finished(raw):
    return replace(raw, party_pp=((1, 35, 0, 0), (12, 10, 0, 0)),
                   bag_items=((53, 3), (4, 2)), bag_item_ids=(53, 4))


def test_selects_nonlead_by_real_gain_and_verifies_literal_complete_effect():
    raw = state()
    plan = plan_field_elixir(raw)
    assert plan.party_index == 1
    assert plan.before_pp == (2, 6, 0, 0)
    assert plan.after_pp == (12, 10, 0, 0)
    assert plan.slot_gains == (10, 4, 0, 0)
    assert plan.total_pp_restored == 14
    assert plan.expected_bag == ((53, 3), (4, 2))
    verify_field_elixir(plan, raw, finished(raw))
    with pytest.raises(FrozenInstanceError):
        plan.party_index = 0


def test_pp_ups_clip_without_touching_high_bits_or_empty_slots():
    raw = replace(state(), party_moves=((87, 33, 0, 0), (57, 58, 45, 0)),
                  party_pp=((10, 35, 0, 0), (0xC2, 0x4B, 0xF8, 0)),
                  first_party_pp=(10, 35, 0, 0))
    plan = plan_field_elixir(raw)
    # Surf max24, Ice Beam max12, Growl max61 (PP-Up bonus capped at7).
    assert plan.after_pp == (0xCC, 0x4C, 0xFD, 0)
    assert plan.slot_gains == (10, 1, 5, 0)
    after = replace(raw, party_pp=((10, 35, 0, 0), (0xCC, 0x4C, 0xFD, 0)),
                    bag_items=((53, 3), (4, 2)), bag_item_ids=(53, 4))
    verify_field_elixir(plan, raw, after)


def test_tie_uses_first_index_and_updates_lead_alias_without_reordering():
    raw = replace(state(), party_pp=((1, 35, 0, 0), (6, 10, 0, 0)),
                  bag_items=((53, 3), (82, 2), (4, 2)))
    plan = plan_field_elixir(raw)
    assert plan.party_index == 0 and plan.slot_gains == (9, 0, 0, 0)
    assert plan.expected_bag == ((53, 3), (82, 1), (4, 2))
    verify_field_elixir(plan, raw, replace(
        raw, party_pp=((10, 35, 0, 0), (6, 10, 0, 0)), first_party_pp=(10, 35, 0, 0),
        bag_items=((53, 3), (82, 1), (4, 2)),
    ))


def test_status_does_not_forbid_living_target_and_is_preserved():
    raw = replace(state(), party_status=(0, 64))
    plan = plan_field_elixir(raw)
    assert plan.party_index == 1
    verify_field_elixir(plan, raw, finished(raw))


@pytest.mark.parametrize("change", [
    {"game_started": 1}, {"battle_state": False}, {"battle_state": 2},
    {"party_count": True}, {"player_money": True}, {"event_flags": bytes(318)},
    {"event_flags": bytes(320)},
    {"party_hp": (118, 0)}, {"party_hp": (118, 218)}, {"party_status": (0, False)},
    {"party_levels": (56, 101)}, {"party_species_ids": (104, 0)},
    {"party_moves": ((87, 33, 0, 0), (57, 58, 0))},
    {"party_pp": ((1, 35, 0, 0), (16, 6, 0, 0))},
    {"party_pp": ((1, 35, 0, 0), (2, 6, 0, 64))},
    {"party_pp": ((1, 35, 0, 0), (True, 6, 0, 0))},
    {"party_moves": ((87, 33, 0, 0), (0, 0, 0, 0)),
     "party_pp": ((1, 35, 0, 0), (0, 0, 0, 0))},
    {"bag_items": ((53, 3), (4, 2)), "bag_item_ids": (53, 4)},
    {"bag_items": ((82, 1), (82, 1))}, {"bag_items": ((82, True),)},
    {"bag_items": ((82, 0),)}, {"first_party_pp": (10, 35, 0, 0)},
    {"active_party_index": 0}, {"enemy_hp": []}, {"enemy_using_trapping_move": 1},
])
def test_bad_or_unfunded_plans_refuse(change):
    with pytest.raises(RedElixirPlanError):
        plan_field_elixir(replace(state(), **change))


def test_full_pp_refuses_without_an_artificial_target():
    raw = replace(state(), party_pp=((10, 35, 0, 0), (15, 10, 0, 0)),
                  first_party_pp=(10, 35, 0, 0))
    with pytest.raises(RedElixirPlanError, match="positive PP benefit"):
        plan_field_elixir(raw)


@pytest.mark.parametrize("change", [
    {"party_pp": ((10, 35, 0, 0), (2, 6, 0, 0)), "first_party_pp": (10, 35, 0, 0)},
    {"party_pp": ((2, 35, 0, 0), (12, 10, 0, 0)), "first_party_pp": (2, 35, 0, 0)},
    {"party_pp": ((1, 35, 0, 0), (15, 10, 0, 0))},
    {"bag_items": ((53, 2), (4, 2))},
    {"bag_items": ((53, 3), (82, 1), (4, 2)), "bag_item_ids": (53, 82, 4)},
    {"bag_items": ((4, 2), (53, 3)), "bag_item_ids": (4, 53)},
    {"party_hp": (118, 165)}, {"party_status": (0, 64)},
    {"party_levels": (56, 68)}, {"party_species_ids": (104, 29)},
    {"party_moves": ((87, 33, 0, 0), (57, 59, 0, 0))},
    {"player_money": 1235}, {"map_id": 114}, {"player_x": 7}, {"player_y": 3},
    {"event_flags": bytes([1]) + bytes(318)}, {"badge_bits": 254},
    {"status_flags_1": 1}, {"repel_remaining_steps": 1}, {"bag_item_ids": (53, 82, 4)},
])
def test_wrong_effect_extra_consumption_and_unrelated_mutations_refuse(change):
    raw = state()
    with pytest.raises(RedElixirPlanError):
        verify_field_elixir(plan_field_elixir(raw), raw, replace(finished(raw), **change))


def test_before_snapshot_and_forged_plan_refuse():
    raw = state()
    plan = plan_field_elixir(raw)
    with pytest.raises(RedElixirPlanError, match="bound snapshot"):
        verify_field_elixir(plan, replace(raw, player_money=1235), finished(raw))
    with pytest.raises(RedElixirPlanError, match="bound observed benefit"):
        replace(plan, party_index=True)
    with pytest.raises(RedElixirPlanError, match="bound observed benefit"):
        replace(plan, slot_gains=(10, 3, 0, 0))


def test_consuming_two_elixirs_instead_of_one_refuses():
    raw = replace(state(), bag_items=((53, 3), (82, 2), (4, 2)))
    with pytest.raises(RedElixirPlanError, match="one-item consumption"):
        verify_field_elixir(plan_field_elixir(raw), raw, finished(raw))


def test_field_enemy_scratch_aliases_are_not_claimed_as_preserved_game_state():
    raw = state()
    verify_field_elixir(plan_field_elixir(raw), raw, replace(finished(raw), enemy_hp=99))
