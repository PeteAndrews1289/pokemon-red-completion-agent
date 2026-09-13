from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.observation import ItemId, MapId, RawGameState
from pokemon_red_completion.red_capture_funding_budget import (
    RedCaptureFundingBudget,
    red_capture_funding_budget,
)
from pokemon_red_completion.red_goal_skills import RedMartPurchase, RedMartResupplyGoalProvider


def setup(*, cash=593, bag=(), count=0, target=20):
    raw = RawGameState(True, 154, 3, 3, 6, 0, player_money=cash, bag_items=bag)
    observation = SimpleNamespace(raw=raw, capture_item_count=count)
    provider = RedMartResupplyGoalProvider(
        map_id=MapId.FUCHSIA_MART, player_x=3, player_y=3, interaction_direction="up",
        purchases=(RedMartPurchase(0, ItemId.ULTRA_BALL, 20, 1200),),
        actions=None, reader=None, emulator=None,
        adapter=SimpleNamespace(config=SimpleNamespace(desired_capture_items=target)),
        affordable_ball_purchase=True,
    )
    return observation, provider


def test_cash_target_derives_from_missing_supply_not_a_free_scalar():
    observation, provider = setup()
    budget = red_capture_funding_budget(observation, provider)
    assert budget.target_cash == 24000 and budget.shortfall == 23407
    assert budget.required_quantity == 20
    # Existing stock can be another interchangeable ball type.
    observation, provider = setup(bag=((4, 12),), count=12)
    budget = red_capture_funding_budget(observation, provider)
    assert budget.target_cash == 9600 and budget.required_quantity == 8


def test_quantity_price_headroom_and_satisfied_reserve():
    b = RedCaptureFundingBudget(100, 97, 110, 20, 97, 600)
    assert b.required_quantity == 2 and b.target_cash == 1200 and b.shortfall == 1100
    assert replace(b, reserve_target=90).target_cash == 0
    assert replace(b, available_funds=2000).shortfall == 0
    assert replace(b, purchase_limit=1).required_quantity == 1


def test_unknown_or_storage_blocked_does_not_offer_a_cash_solution():
    observation, provider = setup(cash=None)
    assert red_capture_funding_budget(observation, provider) is None
    observation, provider = setup(bag=tuple((i, 1) for i in range(20, 40)))
    assert red_capture_funding_budget(observation, provider) is None
    observation, provider = setup()
    assert red_capture_funding_budget(
        observation, replace(provider, affordable_ball_purchase=False)
    ) is None
    observation, provider = setup(bag=((4, 12),), count=0)
    with pytest.raises(ValueError, match="disagrees"):
        red_capture_funding_budget(observation, provider)


@pytest.mark.parametrize("change", [
    {"unit_price": 0}, {"purchase_limit": 0}, {"reserve_target": True},
    {"priced_item_stock": 100}, {"available_funds": 1000000},
    {"available_capture_items": 0},
])
def test_budget_rejects_invalid_or_contradictory_inputs(change):
    with pytest.raises(ValueError):
        replace(RedCaptureFundingBudget(593, 1, 20, 20, 1, 1200), **change)
