from dataclasses import replace

import pytest
from test_red_resource_goal_router import _Port, _supply
from test_red_resource_goal_router import fixture as routed_fixture

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.goal_resource_quote import affordable_purchase_quantity
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.red_goal_manager import RedGoalOpportunityEnumerator
from pokemon_red_completion.red_goal_skills import RedMartSurplusSale

fixture = routed_fixture


@pytest.mark.parametrize('money,stock,expected', [
    (0, 0, 0), (199, 0, 0), (200, 0, 1), (999, 0, 4),
    (1000, 0, 5), (1109, 0, 5), (2000, 0, 10), (999999, 0, 10),
    (2000, 96, 3), (2000, 99, 0),
])
def test_quantity_uses_integer_cash_batch_and_stack_bounds(money, stock, expected):
    assert affordable_purchase_quantity(available_funds=money, unit_price=200,
        maximum_quantity=10, current_stock=stock, stack_limit=99) == expected


@pytest.mark.parametrize('field,value', [
    ('available_funds', True), ('available_funds', -1), ('unit_price', 0),
    ('maximum_quantity', 0), ('current_stock', 100), ('stack_limit', 0),
])
def test_invalid_costs_fail_closed(field, value):
    parameters = dict(available_funds=1109, unit_price=200, maximum_quantity=10,
                      current_stock=0, stack_limit=99)
    parameters[field] = value
    with pytest.raises(ValueError):
        affordable_purchase_quantity(**parameters)


def enable(f):
    provider = replace(f.provider, affordable_ball_purchase=True)
    f.router.runtime.provider_for = lambda *_: provider
    f.router.runtime.enumerator = lambda _: RedGoalOpportunityEnumerator((provider,))
    f.reader.raw = replace(f.reader.raw, player_money=1109)
    f.router.quote_resource_costs = True
    return provider


@pytest.mark.parametrize('at_clerk', [True, False])
def test_actual_partial_purchase_matches_quoted_cash_and_quantity(fixture, at_clerk):
    f = fixture
    provider = enable(f)
    if at_clerk:
        f.reader.raw = replace(f.reader.raw, player_x=4)
    observed = f.adapter.observe()
    fixed = provider.affordable_provider(observed)
    assert fixed.purchases[0].quantity == 5 and not fixed.affordable_ball_purchase
    binding_set = f.router.enumerate(observed)
    offered = _supply(binding_set)
    assert offered.resource_quote.purchase_cost == 1000
    assert offered.resource_quote.available_funds == 1109
    assert offered.resource_quote.funding_proceeds == 0
    assert f.actions.actions_executed == 0
    binding = binding_set.require(offered.binding_ref)
    result = binding.execute()
    assert binding.verify(result).status.value == 'succeeded'
    assert f.reader.raw.player_money == 109
    assert dict(f.reader.raw.bag_items)[int(ItemId.POKE_BALL)] == 5


def test_earned_money_in_transit_cannot_increase_the_declared_purchase(fixture, monkeypatch):
    f = fixture
    enable(f)
    bindings = f.router.enumerate(f.adapter.observe())
    offered = _supply(bindings)
    assert offered.resource_quote.purchase_cost == 1000
    original_execute = _Port.execute
    def earning(port, action):
        result = original_execute(port, action)
        if action.kind is MacroActionKind.MOVE and action.value == 'right':
            port.reader.raw = replace(port.reader.raw, player_money=3109)
        return result
    monkeypatch.setattr(_Port, 'execute', earning)
    binding = bindings.require(offered.binding_ref)
    report = binding.execute()
    assert binding.verify(report).status.value == 'succeeded'
    assert f.reader.raw.player_money == 2109
    assert dict(f.reader.raw.bag_items)[int(ItemId.POKE_BALL)] == 5


def test_insufficient_money_is_unavailable_without_a_sale(fixture):
    f = fixture
    provider = enable(f)
    f.reader.raw = replace(f.reader.raw, player_money=199)
    observation = f.adapter.observe()
    assert provider.affordable_provider(observation) is None
    assert not provider.resource_availability(observation).executable
    assert provider.offer(observation).binding is None
    assert f.actions.actions_executed == 0
    with pytest.raises(ValueError, match='no sale'):
        replace(provider, funding_sale=RedMartSurplusSale(ItemId.HYPER_POTION, 3, 8))
