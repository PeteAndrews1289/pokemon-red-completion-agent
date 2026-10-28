"""Pure no-sale supply arithmetic shared by chapter admission and purchasing."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SupplyRequirement:
    item_id: int
    target_quantity: int
    unit_price: int

    def __post_init__(self):
        for name in ("item_id", "target_quantity", "unit_price"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError("supply requirements need positive integers")
        if self.target_quantity > 99:
            raise ValueError("supply target exceeds one inventory stack")


@dataclass(frozen=True)
class NoSaleSupplyPlan:
    # (item, carried, target, buy, unit price); surplus is never sold.
    rows: tuple[tuple[int, int, int, int, int], ...]
    available_cash: int
    recovery_buffer: int

    @property
    def purchase_cost(self):
        return sum(buy * price for _, _, _, buy, price in self.rows)

    @property
    def target_cash(self):
        return self.purchase_cost + self.recovery_buffer

    @property
    def shortfall(self):
        return max(0, self.target_cash - self.available_cash)


def plan_no_sale_supplies(bag_items, cash, requirements, *, recovery_buffer=0):
    """Quote current missing stock, not hypothetical post-win funds or sales."""
    if type(cash) is not int or not 0 <= cash <= 999999:
        raise ValueError("supply plan needs observed cash")
    if type(recovery_buffer) is not int or not 0 <= recovery_buffer <= 999999:
        raise ValueError("recovery buffer must be a nonnegative integer")
    bag = {}
    for item, count in bag_items:
        if (type(item) is not int or item <= 0 or item in bag
                or type(count) is not int or not 1 <= count <= 99):
            raise ValueError("supply inventory is incomplete or duplicated")
        bag[item] = count
    requirements = tuple(requirements)
    if any(not isinstance(r, SupplyRequirement) for r in requirements):
        raise TypeError("expected supply requirements")
    if len({r.item_id for r in requirements}) != len(requirements):
        raise ValueError("duplicate supply requirement")
    return NoSaleSupplyPlan(tuple(
        (r.item_id, bag.get(r.item_id, 0), r.target_quantity,
         max(0, r.target_quantity - bag.get(r.item_id, 0)), r.unit_price)
        for r in requirements
    ), cash, recovery_buffer)
