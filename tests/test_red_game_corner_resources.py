from types import SimpleNamespace as NS

import pytest

import pokemon_red_completion.red_game_corner_resources as module
from pokemon_red_completion.observation import PokemonRedStateReader, RamAddress


@pytest.mark.parametrize(
    "coins,price,cash,expected",
    [
        (0, 9999, 11968, (200, 200000, 188032, 9999, 0, False)),
        (0, 9999, 200000, (200, 200000, 0, 9999, 0, True)),
        (9950, 9999, 1000, (1, 1000, 0, 9999, 0, True)),
        (9990, 9999, 999999, None),
        (9989, 9999, 1000, (1, 1000, 0, 9999, 0, True)),
        (9999, 9999, 0, (0, 0, 0, 9999, 0, True)),
        (100, 180, 2000, (2, 2000, 0, 200, 20, True)),
    ],
)
def test_quotes_do_not_conflate_cash_coins_or_ignore_clerk_limit(
    monkeypatch, coins, price, cash, expected
):
    monkeypatch.setattr(module, "authenticate_coin_vendor", lambda _: (0x45, 50, 1000, 9990, 9999))
    monkeypatch.setattr(module, "game_corner_prizes", lambda _: (NS(species=137, cost=price),))
    quote = module.quote_game_corner_prize(
        b"fixture", species=137, coins=coins, cash=cash, bag=((0x45, 1),)
    )
    if expected is None:
        assert quote is None
    else:
        assert (
            quote.purchases,
            quote.cash_cost,
            quote.cash_shortfall,
            quote.coins_after_purchase,
            quote.coins_after_prize,
            quote.executable_now,
        ) == expected
    assert (
        module.quote_game_corner_prize(b"fixture", species=137, coins=coins, cash=cash, bag=())
        is None
    )


def test_coin_observer_validates_bcd_and_uses_distinct_stock():
    memory = {RamAddress.PLAYER_COINS: 0x98, int(RamAddress.PLAYER_COINS) + 1: 0x76}
    reader = PokemonRedStateReader(NS(read_u8=lambda a: memory.get(a, 0)))
    assert reader.read_game_corner_coins() == 9876
    memory[RamAddress.PLAYER_COINS] = 0xFA
    with pytest.raises(ValueError):
        reader.read_game_corner_coins()


def test_changed_cartridge_cannot_quote_native_currency():
    with pytest.raises(module.CartridgeReadError):
        module.authenticate_coin_vendor(bytes(0x10000))
