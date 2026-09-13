"""Derive a prospective cash target from an existing Red capture-supply offer.

This is a budget for a declared shop/quantity, not proof the shop is reachable or
the cheapest one. Quotes and reserve settings must be retained with the decision.
A future live adapter must re-derive this budget rather than accept an arbitrary
cash target. This helper is not yet connected to live decisions.
"""

from dataclasses import dataclass

from .observation import MAX_BAG_ITEMS
from .red_goal_manager import RedGoalObservation
from .red_goal_skills import _CAPTURE_ITEMS, RedMartResupplyGoalProvider
from .red_resource_economy import red_economy_snapshot


@dataclass(frozen=True, slots=True)
class RedCaptureFundingBudget:
    available_funds: int
    available_capture_items: int
    reserve_target: int
    purchase_limit: int
    priced_item_stock: int
    unit_price: int

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be an observed nonnegative integer")
        if (not self.unit_price or not self.purchase_limit
                or self.priced_item_stock > 99
                or self.priced_item_stock > self.available_capture_items
                or self.available_funds > 999999):
            raise ValueError("capture funding budget bounds differ")

    @property
    def required_quantity(self) -> int:
        return min(max(0, self.reserve_target - self.available_capture_items),
                   self.purchase_limit, 99 - self.priced_item_stock)

    @property
    def target_cash(self) -> int:
        return self.required_quantity * self.unit_price

    @property
    def shortfall(self) -> int:
        return max(0, self.target_cash - self.available_funds)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.capture-funding-budget.v1",
            **{name: getattr(self, name) for name in self.__dataclass_fields__},
            "required_quantity": self.required_quantity,
            "target_cash": self.target_cash,
            "shortfall": self.shortfall,
        }


def red_capture_funding_budget(
    observation: RedGoalObservation, provider: RedMartResupplyGoalProvider,
) -> RedCaptureFundingBudget | None:
    """Use actual class stock and the existing bounded ball-purchase policy.

    Other purchase modes remain unsupported rather than receiving fabricated
    prices or zero budgets. A full bag without this item needs storage first.
    This function does not quote an affordable purchase against unearned income.
    """
    if not isinstance(provider, RedMartResupplyGoalProvider):
        raise TypeError("capture budget requires a real Mart provider")
    if not provider.affordable_ball_purchase:
        return None
    snapshot = red_economy_snapshot(observation.raw)
    if snapshot is None:
        return None
    purchase = provider.purchases[0]  # provider validates one supported ball entry
    bag = dict(observation.raw.bag_items or ())
    actual_capture_items = sum(n for item, n in bag.items() if item in _CAPTURE_ITEMS)
    if observation.capture_item_count != actual_capture_items:
        raise ValueError("capture reserve disagrees with the observed bag")
    stock = bag.get(int(purchase.item), 0)
    if not stock and len(bag) >= MAX_BAG_ITEMS:
        return None
    return RedCaptureFundingBudget(
        available_funds=snapshot.cash,
        available_capture_items=observation.capture_item_count,
        reserve_target=provider.adapter.config.desired_capture_items,
        purchase_limit=purchase.quantity,
        priced_item_stock=stock,
        unit_price=purchase.unit_price,
    )
