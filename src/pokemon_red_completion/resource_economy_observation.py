"""Prospective economy observations; no historical rewards or policies change.

Quotes are conditional features, never observed proceeds. Signed cash changes
and per-item net inventory changes are separate targets: snapshots cannot prove
gross earnings, spending, or consumption followed by replenishment. Callers must
retain action/time/party costs and choice-admission evidence alongside these facts.
"""

import math
from dataclasses import dataclass
from enum import StrEnum

ECONOMY_SCHEMA = "pokemon.core.resource-economy-snapshot.v1"
ECONOMY_FEATURE_NAMES = (
    "earning", "purchasing", "cash_shortfall", "conditional_income",
    "planned_spend", "shortfall_income",
)


def _count(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class EconomySnapshot:
    cash: int
    inventory: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        _count(self.cash, "cash")
        if type(self.inventory) is not tuple:
            raise ValueError("inventory must be an immutable item ledger")
        keys = []
        for entry in self.inventory:
            if type(entry) is not tuple or len(entry) != 2:
                raise ValueError("inventory entries must be key/count pairs")
            key, count = entry
            if not isinstance(key, str) or not key or not key.isascii():
                raise ValueError("inventory keys must be nonempty ASCII identifiers")
            _count(count, "item count")
            if count == 0:
                raise ValueError("omit zero-count inventory entries")
            keys.append(key)
        if keys != sorted(set(keys)):
            raise ValueError("inventory keys must be unique and sorted")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": ECONOMY_SCHEMA, "cash": self.cash,
            "inventory": [[key, count] for key, count in self.inventory],
        }


class EconomyMode(StrEnum):
    EARN = "earn"
    PURCHASE = "purchase"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class EconomyOffer:
    mode: EconomyMode
    conditional_income: int = 0
    planned_spend: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.mode, EconomyMode):
            raise ValueError("economy mode must be explicit")
        _count(self.conditional_income, "conditional income")
        _count(self.planned_spend, "planned spend")
        if self.mode != EconomyMode.EARN and self.conditional_income:
            raise ValueError("only an earning offer may quote income")


def economy_features(
    before: EconomySnapshot, offer: EconomyOffer, *, target_cash: int,
) -> tuple[float, ...]:
    """Identity-free prospective features, relative to a declared useful budget.

    Budget must come from unmet supply needs, not a goal to maximize money. An
    executor still has to prove affordability/access; this function authorizes
    nothing. No current model consumes this new feature schema implicitly.
    """
    _count(target_cash, "target cash")
    scale = max(1, target_cash)
    shortfall = max(0, target_cash - before.cash) / scale
    income = min(1.0, offer.conditional_income / scale)
    return (
        float(offer.mode == EconomyMode.EARN),
        float(offer.mode == EconomyMode.PURCHASE),
        shortfall, income, min(1.0, offer.planned_spend / scale),
        shortfall * income,
    )


@dataclass(frozen=True, slots=True)
class EconomyOutcome:
    cash_delta: int
    net_item_decrease: int
    net_item_increase: int
    useful_liquidity_gain: float
    cash_loss: float

    def __post_init__(self) -> None:
        if type(self.cash_delta) is not int:
            raise ValueError("cash delta must be a signed integer")
        _count(self.net_item_decrease, "net item decrease")
        _count(self.net_item_increase, "net item increase")
        for name in ("useful_liquidity_gain", "cash_loss"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be a finite normalized number")
        if self.cash_delta <= 0 and self.useful_liquidity_gain != 0:
            raise ValueError("nonpositive cash change cannot prove liquidity gain")
        if self.cash_delta >= 0 and self.cash_loss != 0:
            raise ValueError("nonnegative cash change cannot prove cash loss")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.resource-economy-outcome.v1",
            "cash_delta": self.cash_delta,
            "net_item_decrease": self.net_item_decrease,
            "net_item_increase": self.net_item_increase,
            "useful_liquidity_gain": self.useful_liquidity_gain,
            "cash_loss": self.cash_loss,
            # Endpoint differences cannot identify either gross flow.
            "gross_income": None, "gross_spend": None,
        }


def economy_outcome(
    before: EconomySnapshot | None, after: EconomySnapshot | None, *,
    target_cash: int, interrupted: bool = False,
) -> EconomyOutcome | None:
    """Censor missing/interrupted data, never substitute a quote or zero money.

    Positive gain is capped by the *before* unmet funding budget. A purchase's
    cash decrease remains a cost, with its items recorded separately; this is
    not a standalone scalar reward and must not discourage useful purchases.
    Failed but settled choices retain actual losses. Status is recorded by the
    parent outcome, not inferred from cash movement.
    """
    _count(target_cash, "target cash")
    if type(interrupted) is not bool:
        raise ValueError("interrupted must be boolean")
    if interrupted or before is None or after is None:
        return None
    old, new = dict(before.inventory), dict(after.inventory)
    keys = old.keys() | new.keys()
    delta = after.cash - before.cash
    scale = max(1, target_cash)
    return EconomyOutcome(
        cash_delta=delta,
        net_item_decrease=sum(max(0, old.get(k, 0) - new.get(k, 0)) for k in keys),
        net_item_increase=sum(max(0, new.get(k, 0) - old.get(k, 0)) for k in keys),
        useful_liquidity_gain=min(max(0, delta), max(0, target_cash - before.cash)) / scale,
        cash_loss=min(1.0, max(0, -delta) / scale),
    )
