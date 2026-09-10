"""Known economic facts beside learned outcomes, never replacement training labels."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


def _count(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def affordable_purchase_quantity(
    *, available_funds: int, unit_price: int, maximum_quantity: int,
    current_stock: int, stack_limit: int,
) -> int:
    """Integer-only bounded quantity from actual cash and inventory headroom.

    Zero means no legal purchase. No borrowing, implied sale, replenishment,
    desired outcome or model score participates in these known economic facts.
    """
    for name, value in (
        ("funds", available_funds), ("unit price", unit_price),
        ("maximum quantity", maximum_quantity), ("current stock", current_stock),
        ("stack limit", stack_limit),
    ):
        _count(value, name)
    if not unit_price or not maximum_quantity or not stack_limit or current_stock > stack_limit:
        raise ValueError("affordable purchase bounds differ")
    return min(maximum_quantity, available_funds // unit_price, stack_limit - current_stock)


@dataclass(frozen=True, slots=True)
class GoalResourceReserve:
    """An interchangeable resource class, without item or title identity."""

    resource: str
    available: int
    target: int
    purchased: int

    def __post_init__(self) -> None:
        if self.resource not in {"capture", "recovery"}:
            raise ValueError("resource class is unsupported")
        for name in ("available", "target", "purchased"):
            _count(getattr(self, name), name)
        if self.purchased == 0:
            raise ValueError("quoted reserve must include a purchase")

    @property
    def excess_purchased(self) -> int:
        return max(0, self.purchased - max(0, self.target - self.available))

    def public_dict(self) -> dict[str, object]:
        return {
            "resource": self.resource,
            "available": self.available,
            "target": self.target,
            "purchased": self.purchased,
        }


@dataclass(frozen=True, slots=True)
class GoalResourceQuote:
    """A fresh exact purchase quote with a prospective, explicit cost contract.

    The penalty is spend/funds plus the fraction of bought units above declared
    reserve targets. Both are dimensionless known facts. The caller applies its
    existing resource-cost weight; no predicted outcome or prior label changes.
    An explicitly funded V2 quote keeps real cash separate from sale proceeds;
    V1 bytes and semantics remain unchanged. Proceeds are finite, not free cash.
    V3 describes conditional income only: no purchased stock, advance credit,
    negative cost or success label. Execution must prove the actual earnings.
    V4 is a bounded owned-item consumption allowance, not predicted spending.
    """

    available_funds: int
    purchase_cost: int
    reserves: tuple[GoalResourceReserve, ...]
    funding_proceeds: int = 0
    expected_income: int = 0
    available_recovery_units: int | None = None
    maximum_recovery_consumption: int = 0

    def __post_init__(self) -> None:
        _count(self.available_funds, "available funds")
        _count(self.purchase_cost, "purchase cost")
        _count(self.funding_proceeds, "funding proceeds")
        _count(self.expected_income, "expected income")
        _count(self.maximum_recovery_consumption, "maximum recovery consumption")
        if self.available_recovery_units is not None:
            _count(self.available_recovery_units, "available recovery units")
            if (
                not 0 < self.maximum_recovery_consumption <= self.available_recovery_units
                or self.available_funds or self.purchase_cost or self.reserves != ()
                or self.funding_proceeds or self.expected_income
            ):
                raise ValueError(
                    "consumption budget cannot claim purchases, income or absent stock",
                )
            return
        if self.maximum_recovery_consumption:
            raise ValueError("consumption budget requires observed recovery stock")
        if self.expected_income:
            # V3 earns conditional future income; it does not purchase stock,
            # provide spendable funds, or discount cost by an unearned reward.
            if self.purchase_cost != 0 or self.reserves != () or self.funding_proceeds != 0:
                raise ValueError("income quote cannot claim purchases or available proceeds")
            return
        if not 0 < self.purchase_cost <= self.available_funds + self.funding_proceeds:
            raise ValueError("quoted purchase must be positive and affordable")
        if (
            not isinstance(self.reserves, tuple)
            or not self.reserves
            or any(not isinstance(item, GoalResourceReserve) for item in self.reserves)
            or len({item.resource for item in self.reserves}) != len(self.reserves)
        ):
            raise ValueError("quoted reserves must be immutable, typed and unique")
        object.__setattr__(self, "reserves", tuple(sorted(self.reserves, key=lambda x: x.resource)))

    @property
    def cost_units(self) -> float:
        if self.available_recovery_units is not None:
            # Conservative allowance, not a prediction of actual expenditure.
            return self.maximum_recovery_consumption / self.available_recovery_units
        if self.expected_income:
            return 0.0
        purchased = sum(item.purchased for item in self.reserves)
        excess = sum(item.excess_purchased for item in self.reserves)
        return (
            self.purchase_cost / (self.available_funds + self.funding_proceeds) + excess / purchased
        )

    def public_dict(self) -> dict[str, object]:
        if self.available_recovery_units is not None:
            return {
                "schema": "pokemon.core.goal-resource-quote.v4",
                "resource": "recovery", "available_units": self.available_recovery_units,
                "maximum_consumption": self.maximum_recovery_consumption,
                "actual_consumption_predicted": False,
            }
        if self.expected_income:
            return {
                "schema": "pokemon.core.goal-resource-quote.v3",
                "available_funds": self.available_funds,
                "expected_income": self.expected_income,
                "purchase_cost": 0,
                "reserves": [],
            }
        return {
            "schema": (
                "pokemon.core.goal-resource-quote.v2"
                if self.funding_proceeds
                else "pokemon.core.goal-resource-quote.v1"
            ),
            "available_funds": self.available_funds,
            "purchase_cost": self.purchase_cost,
            "reserves": [item.public_dict() for item in self.reserves],
            **({"funding_proceeds": self.funding_proceeds} if self.funding_proceeds else {}),
        }

    @classmethod
    def from_public_dict(cls, value: object) -> GoalResourceQuote:
        if (isinstance(value, Mapping)
                and value.get("schema") == "pokemon.core.goal-resource-quote.v4"):
            if (set(value) != {"schema", "resource", "available_units", "maximum_consumption",
                               "actual_consumption_predicted"}
                    or value["resource"] != "recovery"
                    or value["actual_consumption_predicted"] is not False):
                raise ValueError("consumption budget quote schema differs")
            return cls(0, 0, (),
                       available_recovery_units=_count(value["available_units"], "available units"),
                       maximum_recovery_consumption=_count(value["maximum_consumption"], "budget"))
        if (isinstance(value, Mapping)
                and value.get("schema") == "pokemon.core.goal-resource-quote.v3"):
            if (
                set(value) != {
                    "schema", "available_funds", "expected_income", "purchase_cost", "reserves"
                }
                or type(value["purchase_cost"]) is not int or value["purchase_cost"] != 0
                or not isinstance(value["reserves"], (list, tuple)) or value["reserves"]
            ):
                raise ValueError("income quote schema differs")
            income = _count(value["expected_income"], "expected income")
            if income <= 0:
                raise ValueError("income quote needs positive conditional income")
            return cls(
                _count(value["available_funds"], "available funds"), 0, (),
                expected_income=income,
            )
        funded = (
            isinstance(value, Mapping)
            and value.get("schema") == "pokemon.core.goal-resource-quote.v2"
        )
        if (
            not isinstance(value, Mapping)
            or set(value)
            != {"schema", "available_funds", "purchase_cost", "reserves"}
            | ({"funding_proceeds"} if funded else set())
            or value["schema"]
            not in {"pokemon.core.goal-resource-quote.v1", "pokemon.core.goal-resource-quote.v2"}
            or not isinstance(value["reserves"], (list, tuple))
        ):
            raise ValueError("resource quote schema differs")
        funding = _count(value["funding_proceeds"], "funding proceeds") if funded else 0
        if funded and funding <= 0:
            raise ValueError("funded quote must declare positive sale proceeds")
        reserves = []
        for raw in value["reserves"]:
            if (
                not isinstance(raw, Mapping)
                or set(raw) != {"resource", "available", "target", "purchased"}
                or not isinstance(raw["resource"], str)
            ):
                raise ValueError("resource reserve schema differs")
            reserves.append(
                GoalResourceReserve(
                    resource=raw["resource"],
                    available=_count(raw["available"], "available"),
                    target=_count(raw["target"], "target"),
                    purchased=_count(raw["purchased"], "purchased"),
                )
            )
        return cls(
            available_funds=_count(value["available_funds"], "available funds"),
            purchase_cost=_count(value["purchase_cost"], "purchase cost"),
            reserves=tuple(reserves),
            funding_proceeds=funding,
        )
