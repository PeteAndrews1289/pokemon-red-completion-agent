"""Project one already-observed Red frame into the prospective economy contract."""

from .observation import MAX_BAG_ITEMS, RawGameState
from .resource_economy_observation import EconomySnapshot


def red_economy_snapshot(raw: RawGameState) -> EconomySnapshot | None:
    """Unknown values stay unknown; do not alter legacy public observations.

    Bag identifiers are evidence keys, not model features. PC deposits/withdrawals
    also change this ledger: its deltas are net bag changes, not proof of use.
    No revision-specific memory reads occur outside the observation adapter.
    """
    if raw.player_money is None or raw.bag_items is None:
        return None
    if type(raw.player_money) is not int or not 0 <= raw.player_money <= 999999:
        raise ValueError("Red cash must be a valid observed six-digit amount")
    if type(raw.bag_items) is not tuple or len(raw.bag_items) > MAX_BAG_ITEMS:
        raise ValueError("Red bag must contain at most twenty immutable slots")
    inventory = []
    for entry in raw.bag_items:
        if type(entry) is not tuple or len(entry) != 2:
            raise ValueError("Red bag entries must be immutable item/count pairs")
        item, count = entry
        if type(item) is not int or not 1 <= item <= 255:
            raise ValueError("invalid observed Red item identifier")
        if type(count) is not int or not 1 <= count <= 99:
            raise ValueError("invalid observed Red item quantity")
        inventory.append((f"red-item-{item:03d}", count))
    return EconomySnapshot(raw.player_money, tuple(sorted(inventory)))
