"""Prospective economy facts, not gameplay or model-learning claims."""

from dataclasses import replace

import pytest

from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_resource_economy import red_economy_snapshot
from pokemon_red_completion.resource_economy_observation import (
    ECONOMY_FEATURE_NAMES,
    EconomyMode,
    EconomyOffer,
    EconomyOutcome,
    EconomySnapshot,
    economy_features,
    economy_outcome,
)


def test_quotes_change_features_but_never_observed_proceeds():
    before = EconomySnapshot(200, ())
    lower = economy_features(before, EconomyOffer(EconomyMode.EARN, 300), target_cash=1000)
    higher = economy_features(before, EconomyOffer(EconomyMode.EARN, 600), target_cash=1000)
    assert len(lower) == len(ECONOMY_FEATURE_NAMES) == 6
    assert lower == pytest.approx((1, 0, .8, .3, 0, .24))
    assert higher == pytest.approx((1, 0, .8, .6, 0, .48))
    failed = economy_outcome(before, before, target_cash=1000)
    assert failed.cash_delta == failed.useful_liquidity_gain == 0


def test_rich_state_and_inventory_identity_do_not_fake_need():
    offer = EconomyOffer(EconomyMode.EARN, 600)
    rich = economy_features(EconomySnapshot(2000, ()), offer, target_cash=1000)
    assert rich[2] == rich[5] == 0
    assert economy_features(EconomySnapshot(200, (("a", 1),)), offer, target_cash=1000) == (
        economy_features(EconomySnapshot(200, (("completely-different", 42),)), offer,
                         target_cash=1000)
    )


def test_cash_targets_and_useful_gain_are_bounded_not_hoarding_reward():
    result = economy_outcome(EconomySnapshot(200, ()), EconomySnapshot(5000, ()),
                             target_cash=1000)
    assert result.cash_delta == 4800
    assert result.useful_liquidity_gain == .8
    assert result.cash_loss == 0
    rich = economy_outcome(EconomySnapshot(2000, ()), EconomySnapshot(9000, ()),
                           target_cash=1000)
    assert rich.useful_liquidity_gain == 0
    assert rich.public_dict()["gross_income"] is None
    assert rich.public_dict()["gross_spend"] is None


def test_different_item_net_changes_cannot_cancel_each_other():
    before = EconomySnapshot(1000, (("heal", 2),))
    after = EconomySnapshot(200, (("ball", 4), ("heal", 1)))
    outcome = economy_outcome(before, after, target_cash=1000)
    assert outcome.cash_delta == -800
    assert outcome.cash_loss == .8
    assert outcome.useful_liquidity_gain == 0
    assert outcome.net_item_decrease == 1
    assert outcome.net_item_increase == 4


def test_income_and_spending_are_net_only_without_transaction_evidence():
    # Could represent +1000 and -600; endpoints prove only +400 and two items.
    outcome = economy_outcome(EconomySnapshot(200, ()),
                              EconomySnapshot(600, (("ball", 2),)), target_cash=1000)
    assert outcome.cash_delta == 400
    assert outcome.net_item_increase == 2
    assert outcome.public_dict()["gross_income"] is None


@pytest.mark.parametrize("before,after,interrupted", [
    (None, EconomySnapshot(0, ()), False),
    (EconomySnapshot(0, ()), None, False),
    (EconomySnapshot(0, ()), EconomySnapshot(100, ()), True),
])
def test_missing_or_interrupted_cash_is_censored(before, after, interrupted):
    assert economy_outcome(before, after, target_cash=1000, interrupted=interrupted) is None


def test_zero_budget_and_cash_loss_edges():
    a, b = EconomySnapshot(0, ()), EconomySnapshot(99, ())
    assert economy_outcome(a, b, target_cash=0).useful_liquidity_gain == 0
    assert economy_outcome(b, a, target_cash=0).cash_loss == 1
    assert economy_features(a, EconomyOffer(EconomyMode.OTHER), target_cash=0) == (0,) * 6


@pytest.mark.parametrize("cash", [True, -1, 1.5, "500"])
def test_rejects_bad_cash(cash):
    with pytest.raises(ValueError):
        EconomySnapshot(cash, ())


@pytest.mark.parametrize("inventory", [
    (("a", 1), ("a", 2)), (("b", 1), ("a", 2)), (("a", 0),),
    (("a", True),), (("a", -1),), (("", 2),), [["a", 2]],
])
def test_rejects_ambiguous_inventory(inventory):
    with pytest.raises(ValueError):
        EconomySnapshot(0, inventory)


@pytest.mark.parametrize("kwargs", [
    {"mode": "earn"}, {"mode": EconomyMode.OTHER, "conditional_income": 1},
    {"mode": EconomyMode.EARN, "conditional_income": -1},
    {"mode": EconomyMode.PURCHASE, "planned_spend": True},
])
def test_rejects_bad_offer(kwargs):
    with pytest.raises(ValueError):
        EconomyOffer(**kwargs)


def test_red_projection_keeps_unknown_distinct_and_inventory_non_mutating():
    raw = RawGameState(True, 1, 1, 1, 0, 0,
                       player_money=593, bag_items=((20, 2), (4, 1)))
    snapshot = red_economy_snapshot(raw)
    assert snapshot == EconomySnapshot(593, (("red-item-004", 1), ("red-item-020", 2)))
    assert raw.bag_items == ((20, 2), (4, 1))
    assert red_economy_snapshot(replace(raw, player_money=None)) is None
    assert red_economy_snapshot(replace(raw, bag_items=None)) is None
    empty = red_economy_snapshot(replace(raw, player_money=0, bag_items=()))
    assert empty == EconomySnapshot(0, ())


@pytest.mark.parametrize("cash,bag", [
    (1000000, ()), (True, ()), (0, ((0, 1),)), (0, ((4, 100),)),
    (0, ((4, 1), (4, 2))), (0, ((True, 1),)),
    (0, tuple((i, 1) for i in range(1, 22))), (0, [(4, 1)]),
    (0, ([4, 1],)), (0, ((4,),)),
])
def test_red_projection_rejects_malformed_evidence(cash, bag):
    with pytest.raises(ValueError):
        red_economy_snapshot(RawGameState(True, 1, 1, 1, 0, 0,
                                         player_money=cash, bag_items=bag))


def test_same_item_replenishment_is_unknown_consumption_not_zero_use_claim():
    same = EconomySnapshot(100, (("heal", 2),))
    result = economy_outcome(same, same, target_cash=1000)
    assert result.net_item_decrease == result.net_item_increase == 0
    assert "consumed_items" not in result.public_dict()


@pytest.mark.parametrize("values", [
    (0, -1, 0, 0, 0), (0, 0, True, 0, 0), (0, 0, 0, float("nan"), 0),
    (0, 0, 0, 0, 1.1), (10, 0, 0, 0, .1), (-10, 0, 0, .1, 0),
    (False, 0, 0, 0, 0), (0, 0, 0, True, 0),
])
def test_direct_outcomes_cannot_publish_invalid_evidence(values):
    with pytest.raises(ValueError):
        EconomyOutcome(*values)


def test_prospective_snapshot_does_not_reuse_legacy_schema():
    from pokemon_red_completion.resource_economy import ResourceEconomyState

    assert ResourceEconomyState is not None
    assert EconomySnapshot(0, ()).public_dict()["schema"] == (
        "pokemon.core.resource-economy-snapshot.v1"
    )
