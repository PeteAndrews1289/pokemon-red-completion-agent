from dataclasses import replace

import pytest
from test_red_goal_context_profile import _supply_transition_profile
from test_red_goal_skills import _adapter, _MartPort, _raw, _Reader

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_resource_quote import GoalResourceQuote, GoalResourceReserve
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
    require_resupply_only_profile_transition,
)
from pokemon_red_completion.red_goal_skills import (
    RedGoalSkillError,
    RedMartPurchase,
    RedMartResupplyGoalProvider,
    RedMartSurplusSale,
)


def _provider(*, potions=11, funds=129):
    raw = replace(
        _raw(hyper_potions=potions, poke_balls=0),
        map_id=MapId.CERULEAN_MART,
        player_x=2,
        player_y=5,
        player_money=funds,
    )
    bag = {
        **dict(raw.bag_items),
        int(ItemId.HELIX_FOSSIL): 1,
        int(ItemId.FULL_RESTORE): 7,
        int(ItemId.REVIVE): 3,
    }
    reader = _Reader(
        raw=replace(raw, bag_item_ids=tuple(bag), bag_items=tuple(bag.items())), ready=True
    )
    port = _MartPort(reader)
    actions = CountingExecutor(port)
    return RedMartResupplyGoalProvider(
        MapId.CERULEAN_MART,
        2,
        5,
        "left",
        (RedMartPurchase(0, ItemId.POKE_BALL, 10, 200),),
        actions,
        reader,
        port,
        _adapter(reader),
        funding_sale=RedMartSurplusSale(ItemId.HYPER_POTION, 3, 8),
    )


def test_funded_quote_keeps_actual_cash_separate_and_preserves_legacy_encoding():
    quote = GoalResourceQuote(129, 2000, (GoalResourceReserve("capture", 0, 10, 10),), 2250)
    assert quote.cost_units == pytest.approx(2000 / 2379)
    assert quote.public_dict()["available_funds"] == 129
    assert quote.public_dict()["funding_proceeds"] == 2250
    assert GoalResourceQuote.from_public_dict(quote.public_dict()) == quote
    legacy = GoalResourceQuote(3000, 2000, quote.reserves)
    assert legacy.public_dict()["schema"] == "pokemon.core.goal-resource-quote.v1"
    assert "funding_proceeds" not in legacy.public_dict()
    assert GoalResourceQuote.from_public_dict(legacy.public_dict()) == legacy
    for damage in (
        {"funding_proceeds": 0},
        {"funding_proceeds": True},
        {"schema": "pokemon.core.goal-resource-quote.v1"},
        {"funding_proceeds": 1},
    ):
        with pytest.raises(ValueError):
            GoalResourceQuote.from_public_dict({**quote.public_dict(), **damage})


def test_surplus_funding_requires_real_stock_and_skips_sale_if_already_affordable():
    provider = _provider()
    observation = provider.adapter.observe()
    assert provider.resource_availability(observation).executable
    quote = provider.resource_quote(observation)
    assert quote.available_funds == 129 and quote.funding_proceeds == 2250
    assert provider.actions.actions_executed == 0
    short = _provider(potions=10)
    assert (
        short.resource_availability(short.adapter.observe()).unavailable_reason
        is GoalUnavailableReason.MISSING_RESOURCE
    )
    funded = _provider(potions=10, funds=2000)
    assert funded.resource_quote(funded.adapter.observe()).funding_proceeds == 0
    for item, quantity, reserve in (
        (ItemId.HELIX_FOSSIL, 1, 8),
        (ItemId.HYPER_POTION, 3, 7),
        (ItemId.HYPER_POTION, True, 8),
    ):
        with pytest.raises(ValueError):
            RedMartSurplusSale(item, quantity, reserve)


@pytest.mark.parametrize("damage", [None, "money", "protected", "party"])
def test_sale_and_purchase_verify_both_ledger_sides_before_success(monkeypatch, damage):
    provider = _provider()
    reader = provider.reader
    events = []

    def sale(actions, _reader, _emulator, _timing, item, *, quantity, expected_proceeds):
        assert item is ItemId.HYPER_POTION and quantity == 3 and expected_proceeds == 2250
        bag = dict(reader.raw.bag_items)
        bag[int(ItemId.HYPER_POTION)] -= 3
        if damage == "protected":
            bag.pop(int(ItemId.HELIX_FOSSIL))
        reader.raw = replace(
            reader.raw,
            bag_items=tuple(bag.items()),
            bag_item_ids=tuple(bag),
            player_money=2378 if damage == "money" else 2379,
            party_hp=(1,) if damage == "party" else reader.raw.party_hp,
        )
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        events.append("sale")

    def buy(actions, _emulator, _timing, **kwargs):
        assert events == ["sale"] and reader.raw.player_money == 2379
        assert kwargs["quantity"] == 10 and kwargs["target_bag_quantity"] == 10
        bag = dict(reader.raw.bag_items)
        bag[int(ItemId.POKE_BALL)] = 10
        reader.raw = replace(
            reader.raw, bag_items=tuple(bag.items()), bag_item_ids=tuple(bag), player_money=379
        )
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        events.append("buy")

    monkeypatch.setattr("pokemon_red_completion.red_goal_skills._sell_mart_item_stack", sale)
    monkeypatch.setattr("pokemon_red_completion.red_goal_skills._buy_mart_item", buy)
    monkeypatch.setattr("pokemon_red_completion.red_goal_skills._close_menus", lambda *_: None)
    offer = provider.offer(provider.adapter.observe())
    assert offer.binding is not None
    if damage:
        with pytest.raises(RedGoalSkillError, match="protected inventory"):
            offer.binding.execute()
        assert events == ["sale"]
    else:
        report = offer.binding.execute()
        assert offer.binding.verify(report).status.value == "succeeded"
        assert events == ["sale", "buy"] and reader.raw.player_money == 379
        assert dict(reader.raw.bag_items)[int(ItemId.HYPER_POTION)] == 8
        assert report.evidence["sale_proceeds"] == 2250


def test_stale_stock_cannot_sell_through_the_retained_reserve(monkeypatch):
    provider = _provider()
    offer = provider.offer(provider.adapter.observe())
    bag = dict(provider.reader.raw.bag_items)
    bag[int(ItemId.HYPER_POTION)] = 8
    provider.reader.raw = replace(provider.reader.raw, bag_items=tuple(bag.items()))
    monkeypatch.setattr(
        "pokemon_red_completion.red_goal_skills._sell_mart_item_stack",
        lambda *_a, **_k: pytest.fail("sold stale reserve"),
    )
    with pytest.raises(RedGoalSkillError, match="changed before sale"):
        offer.binding.execute()


@pytest.mark.parametrize("damage", [None, "item", "reserve", "extra"])
def test_optional_funding_profile_is_explicit_and_protected(damage):
    original = _supply_transition_profile()
    providers = []
    for spec in original.providers:
        params = _thaw(spec.parameters)
        if spec.kind is GoalKind.RESUPPLY:
            params["funding_sale"] = {
                "item_id": int(ItemId.HYPER_POTION),
                "quantity": 3,
                "minimum_retained": 8,
            }
            if damage == "item":
                params["funding_sale"]["item_id"] = int(ItemId.HELIX_FOSSIL)
            if damage == "reserve":
                params["funding_sale"]["minimum_retained"] = 7
            if damage == "extra":
                params["funding_sale"]["override"] = True
        providers.append((spec.kind, spec.mechanic, params))

    def build():
        return parse_red_goal_context_profile(
            build_red_goal_context_profile_payload(
                profile_id=original.profile_id, providers=tuple(providers)
            )
        )

    if damage:
        with pytest.raises(RedGoalContextProfileError):
            build()
    else:
        updated = build()
        require_resupply_only_profile_transition(original, updated)
        assert updated.profile_sha256 != original.profile_sha256
