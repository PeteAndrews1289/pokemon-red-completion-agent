"""Cartridge-authenticated Game Corner currency and cash procurement quotes.

Separate cash, coins and physical Coin Case. This module quotes purchases; it
does not execute them, authorize gambling, manufacture earnings or promise that
the current player can obtain the shortfall. Pinned source:
pret/pokered 1e96034092686d006e863cace09e87273051a3d8,
scripts/GameCorner.asm and engine/math/bcd.asm.
"""

from dataclasses import dataclass

from .gen1_acquisition import game_corner_prizes
from .gen1_cartridge import CartridgeReadError, bank_offset
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS


@dataclass(frozen=True, slots=True)
class CoinPurchaseQuote:
    coins_before: int
    prize_cost: int
    purchases: int
    cash_cost: int
    cash_shortfall: int
    coins_after_purchase: int
    coins_after_prize: int
    executable_now: bool


def authenticate_coin_vendor(rom):
    """Match the actual pinned consumer, including its money and coin operands."""
    map_id = 0x87
    try:
        bank = rom[MAP_HEADER_BANKS + map_id]
        pointer = MAP_HEADER_POINTERS + 2 * map_id
        header = bank_offset(bank, int.from_bytes(rom[pointer : pointer + 2], "little"))
        texts = bank_offset(bank, int.from_bytes(rom[header + 5 : header + 7], "little"))
        script = bank_offset(bank, int.from_bytes(rom[texts + 2 : texts + 4], "little"))
    except (IndexError, ValueError) as error:
        raise CartridgeReadError("coin vendor pointer differs") from error
    # Entire executable script through TextScriptEnd, not a coincidental address.
    expected = bytes.fromhex(
        "08cd1e4f21224dcd493ccdec35fa26cca720530645cd93342856cd954f304c"
        "afe09fe0a13e10e0a0cda635300521314d1841"
        "afe09fe0a13e10e0a021a1ff1149d30e033e0ccd6d3e"
        "afe09fe0a03e50e0a111a5d521a1ff0e023e0bcd6d3e"
        "cd1e4f21274d180d212c4d180821364d1803213b4dcd493cc3d724"
    )
    if rom[script : script + len(expected)] != expected:
        raise CartridgeReadError("coin vendor script differs")
    return 0x45, 50, 1000, 9990, 9999


def quote_game_corner_prize(rom, *, species, coins, cash, bag):
    """Minimal vendor purchase count, respecting its near-full refusal.

    Native BCD addition saturates at9999. The clerk refuses a new purchase when
    stock is already9990–9999, so e.g.9990cannot be bought up to9999. That is an
    unresolved coin-source dependency, not an ordinary cash shortage.
    """
    case, lot, price, refusal, capacity = authenticate_coin_vendor(rom)
    if (
        type(coins) is not int
        or not 0 <= coins <= capacity
        or type(cash) is not int
        or not 0 <= cash <= 999999
        or type(species) is not int
    ):
        raise ValueError("Game Corner quote needs actual bounded resources")
    offers = tuple(p for p in game_corner_prizes(rom) if p.species == species)
    if len(offers) != 1:
        raise ValueError("no unique cartridge Pokemon prize")
    target = offers[0].cost
    if target is None or target > capacity:
        raise CartridgeReadError("Pokemon prize coin cost differs")
    if dict(bag).get(case, 0) != 1:
        return None
    balance, purchases = coins, 0
    while balance < target:
        if balance >= refusal:
            return None
        balance = min(capacity, balance + lot)
        purchases += 1
    cost = purchases * price
    return CoinPurchaseQuote(
        coins, target, purchases, cost, max(0, cost - cash), balance, balance - target, cash >= cost
    )
