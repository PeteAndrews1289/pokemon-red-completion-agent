"""Known economic facts beside learned outcomes, never replacement training labels."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


def _count(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


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
    """

    available_funds: int
    purchase_cost: int
    reserves: tuple[GoalResourceReserve, ...]

    def __post_init__(self) -> None:
        _count(self.available_funds, "available funds")
        _count(self.purchase_cost, "purchase cost")
        if not 0 < self.purchase_cost <= self.available_funds:
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
        purchased = sum(item.purchased for item in self.reserves)
        excess = sum(item.excess_purchased for item in self.reserves)
        return self.purchase_cost / self.available_funds + excess / purchased

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.goal-resource-quote.v1",
            "available_funds": self.available_funds,
            "purchase_cost": self.purchase_cost,
            "reserves": [item.public_dict() for item in self.reserves],
        }

    @classmethod
    def from_public_dict(cls, value: object) -> GoalResourceQuote:
        if (
            not isinstance(value, Mapping)
            or set(value) != {"schema", "available_funds", "purchase_cost", "reserves"}
            or value["schema"] != "pokemon.core.goal-resource-quote.v1"
            or not isinstance(value["reserves"], (list, tuple))
        ):
            raise ValueError("resource quote schema differs")
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
        )
