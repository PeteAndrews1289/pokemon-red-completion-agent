from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.red_story_funding import silph_supply_plan
from pokemon_red_completion.story_supply import SupplyRequirement, plan_no_sale_supplies


@pytest.mark.parametrize("stock,buy", [(0, 7), (3, 4), (7, 0), (12, 0), (99, 0)])
def test_top_up_preserves_surplus(stock, buy):
    bag = ((18, stock),) if stock else ()
    plan = plan_no_sale_supplies(bag, 10000, (SupplyRequirement(18, 7, 1500),),
                                recovery_buffer=1400)
    assert plan.rows == ((18, stock, 7, buy, 1500),)
    assert plan.purchase_cost == buy * 1500
    assert plan.shortfall == max(0, buy * 1500 + 1400 - 10000)
    assert bag == (((18, stock),) if stock else ())


@pytest.mark.parametrize("bag", [((18, 1), (18, 2)), ((18, 0),), ((18, 100),),
                                 ((18, True),), ((True, 1),)])
def test_bad_inventory_is_not_free_stock(bag):
    with pytest.raises(ValueError):
        plan_no_sale_supplies(bag, 100, ())


@pytest.mark.parametrize("cash,buffer", [(True, 0), (-1, 0), (1000000, 0), (0, True), (0, -1)])
def test_observed_cash_and_explicit_buffer(cash, buffer):
    with pytest.raises(ValueError):
        plan_no_sale_supplies((), cash, (), recovery_buffer=buffer)


def test_duplicate_requirements_cannot_double_charge():
    row = SupplyRequirement(18, 7, 1500)
    with pytest.raises(ValueError):
        plan_no_sale_supplies((), 0, (row, row))
    with pytest.raises(ValueError):
        replace(row, target_quantity=100)


def test_actual_story_supply_budget_is_not_collection_ball_headroom():
    raw = SimpleNamespace(bag_items=((int(ItemId.SUPER_POTION), 4),
                                    (int(ItemId.X_SPECIAL), 1),
                                    (int(ItemId.X_ACCURACY), 2)), player_money=8280)
    plan = silph_supply_plan(raw, recovery_buffer=1400)
    assert plan.purchase_cost == 11550
    assert plan.target_cash == 12950 and plan.shortfall == 4670
    raw.bag_items += ((int(ItemId.HYPER_POTION), 4),)
    assert silph_supply_plan(raw).purchase_cost == 5550
