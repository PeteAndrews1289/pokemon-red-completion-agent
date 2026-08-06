"""Game-neutral resource budgeting for reusable Pokémon curricula.

Game adapters describe shop inventory in semantic roles.  The planner then
computes the least-cost purchase plan that satisfies declared downstream
reserves without knowing cartridge item IDs, menu positions, or money bytes.
These decisions form portable supervision for a future learned resource policy.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum


class ResourcePlanningError(ValueError):
    """Raised when a resource budget is internally inconsistent."""


class ResourceRole(StrEnum):
    CAPTURE = "capture"
    HP_RECOVERY = "hp_recovery"
    STATUS_RECOVERY = "status_recovery"
    REVIVAL = "revival"
    ENCOUNTER_CONTROL = "encounter_control"
    ATTACK_BOOST = "attack_boost"
    SPECIAL_BOOST = "special_boost"
    ACCURACY_BOOST = "accuracy_boost"


@dataclass(frozen=True, slots=True)
class ResourceOffer:
    """One purchasable item expressed through a cross-game semantic role."""

    item_ref: str
    role: ResourceRole
    unit_price: int
    maximum_quantity: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.item_ref, str) or not self.item_ref:
            raise ResourcePlanningError("resource offer item_ref must be non-empty")
        if not isinstance(self.role, ResourceRole):
            raise TypeError("resource offer role must be ResourceRole")
        if type(self.unit_price) is not int or self.unit_price <= 0:  # noqa: E721
            raise ResourcePlanningError("resource offer price must be positive")
        if self.maximum_quantity is not None and (
            type(self.maximum_quantity) is not int or self.maximum_quantity <= 0  # noqa: E721
        ):
            raise ResourcePlanningError("resource offer quantity bound must be positive")


@dataclass(frozen=True, slots=True)
class ResourceRequirement:
    """Minimum quantity of one semantic resource required downstream."""

    role: ResourceRole
    minimum_quantity: int

    def __post_init__(self) -> None:
        if not isinstance(self.role, ResourceRole):
            raise TypeError("resource requirement role must be ResourceRole")
        if type(self.minimum_quantity) is not int or self.minimum_quantity < 0:  # noqa: E721
            raise ResourcePlanningError("resource minimum must be non-negative")


@dataclass(frozen=True, slots=True)
class PlannedPurchase:
    item_ref: str
    role: ResourceRole
    quantity: int
    unit_price: int

    @property
    def cost(self) -> int:
        return self.quantity * self.unit_price


@dataclass(frozen=True, slots=True)
class ResourceShortfall:
    role: ResourceRole
    missing_quantity: int
    minimum_additional_money: int | None


@dataclass(frozen=True, slots=True)
class ResourceBudgetPlan:
    purchases: tuple[PlannedPurchase, ...]
    shortfalls: tuple[ResourceShortfall, ...]
    starting_money: int
    total_cost: int
    money_remaining: int
    final_quantities: tuple[tuple[ResourceRole, int], ...]

    @property
    def funded(self) -> bool:
        return not self.shortfalls

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-resource-budget-plan-v1",
            "funded": self.funded,
            "starting_money": self.starting_money,
            "total_cost": self.total_cost,
            "money_remaining": self.money_remaining,
            "purchases": [
                {
                    "item_ref": item.item_ref,
                    "role": item.role.value,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "cost": item.cost,
                }
                for item in self.purchases
            ],
            "shortfalls": [
                {
                    "role": item.role.value,
                    "missing_quantity": item.missing_quantity,
                    "minimum_additional_money": item.minimum_additional_money,
                }
                for item in self.shortfalls
            ],
            "final_quantities": {
                role.value: quantity for role, quantity in self.final_quantities
            },
        }


def plan_resource_budget(
    *,
    money: int,
    quantities: Mapping[ResourceRole, int],
    requirements: Iterable[ResourceRequirement],
    offers: Iterable[ResourceOffer],
) -> ResourceBudgetPlan:
    """Buy the cheapest available items while preserving every declared reserve.

    Requirements are consolidated by role using the largest declared minimum,
    making composition safe when several upcoming skills share one inventory.
    The result is deterministic and reports unfunded roles instead of silently
    shrinking a completion contract.
    """

    if type(money) is not int or money < 0:  # noqa: E721
        raise ResourcePlanningError("money must be a non-negative integer")
    inventory: Counter[ResourceRole] = Counter()
    for role, quantity in quantities.items():
        if not isinstance(role, ResourceRole):
            raise TypeError("resource quantity keys must be ResourceRole")
        if type(quantity) is not int or quantity < 0:  # noqa: E721
            raise ResourcePlanningError("resource quantities must be non-negative integers")
        inventory[role] = quantity

    required: dict[ResourceRole, int] = {}
    for requirement in requirements:
        if not isinstance(requirement, ResourceRequirement):
            raise TypeError("requirements must contain ResourceRequirement")
        required[requirement.role] = max(
            required.get(requirement.role, 0),
            requirement.minimum_quantity,
        )
    available: dict[ResourceRole, list[ResourceOffer]] = defaultdict(list)
    seen_items: set[str] = set()
    for offer in offers:
        if not isinstance(offer, ResourceOffer):
            raise TypeError("offers must contain ResourceOffer")
        if offer.item_ref in seen_items:
            raise ResourcePlanningError("shop offers duplicate an item_ref")
        seen_items.add(offer.item_ref)
        available[offer.role].append(offer)
    for role in available:
        available[role].sort(key=lambda item: (item.unit_price, item.item_ref))

    remaining_money = money
    purchases: list[PlannedPurchase] = []
    shortfalls: list[ResourceShortfall] = []
    for role in sorted(required, key=lambda item: item.value):
        missing = max(0, required[role] - inventory[role])
        for offer in available.get(role, ()):
            if missing == 0:
                break
            offered = missing
            if offer.maximum_quantity is not None:
                offered = min(offered, offer.maximum_quantity)
            affordable = min(offered, remaining_money // offer.unit_price)
            if affordable:
                purchases.append(
                    PlannedPurchase(
                        item_ref=offer.item_ref,
                        role=role,
                        quantity=affordable,
                        unit_price=offer.unit_price,
                    )
                )
                inventory[role] += affordable
                remaining_money -= affordable * offer.unit_price
                missing -= affordable
        if missing:
            cheapest = available.get(role, ())
            minimum_additional_money = (
                missing * cheapest[0].unit_price - remaining_money if cheapest else None
            )
            shortfalls.append(
                ResourceShortfall(
                    role=role,
                    missing_quantity=missing,
                    minimum_additional_money=(
                        max(0, minimum_additional_money)
                        if minimum_additional_money is not None
                        else None
                    ),
                )
            )
    total_cost = money - remaining_money
    return ResourceBudgetPlan(
        purchases=tuple(purchases),
        shortfalls=tuple(shortfalls),
        starting_money=money,
        total_cost=total_cost,
        money_remaining=remaining_money,
        final_quantities=tuple(sorted(inventory.items(), key=lambda item: item[0].value)),
    )
