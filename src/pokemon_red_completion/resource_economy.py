"""Portable resource-recovery semantics for completion planning.

Raw currency, item identifiers, shop tables, trainer flags, and pickup maps
belong to a title adapter.  The shared planner needs a smaller answer: can the
current capture/recovery reserve support the goal, and if not, which renewal
mechanisms are available, unavailable, or still unknown?
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalUnavailableReason,
)


class ResourceEconomyError(ValueError):
    """Raised when an adapter publishes contradictory economy semantics."""


class ResourceRenewalKind(StrEnum):
    """Cross-title ways a depleted reserve can be renewed."""

    PURCHASE = "purchase"
    EARN = "earn"
    SELL = "sell"
    FIND = "find"


class CollectionResourceDecision(StrEnum):
    """The dependency planner's next resource-aware collection step."""

    ACQUIRE = "acquire"
    REPLENISH = "replenish"
    INVESTIGATE = "investigate"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ResourceRenewalOption:
    """One identity-free replenishment affordance from a title adapter."""

    kind: ResourceRenewalKind
    availability: GoalAvailability
    affordability: float | None = None
    expected_reserve_gain: float | None = None
    unavailable_reason: GoalUnavailableReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ResourceRenewalKind):
            raise ResourceEconomyError("resource renewal kind is invalid")
        if not isinstance(self.availability, GoalAvailability):
            raise ResourceEconomyError("resource renewal availability is invalid")
        for name in ("affordability", "expected_reserve_gain"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _unit(value, subject=name))
        if self.availability is GoalAvailability.AVAILABLE:
            if self.expected_reserve_gain is None or self.expected_reserve_gain <= 0.0:
                raise ResourceEconomyError(
                    "an available renewal needs a positive normalized reserve gain"
                )
            if self.unavailable_reason is not None:
                raise ResourceEconomyError(
                    "an available renewal cannot carry an unavailable reason"
                )
            if self.kind is ResourceRenewalKind.PURCHASE and self.affordability is None:
                raise ResourceEconomyError(
                    "a purchase renewal needs normalized affordability"
                )
        else:
            if self.expected_reserve_gain is not None:
                raise ResourceEconomyError(
                    "a masked renewal cannot promise a reserve gain"
                )
            if not isinstance(self.unavailable_reason, GoalUnavailableReason):
                raise ResourceEconomyError(
                    "a masked renewal needs a portable unavailable reason"
                )

    def public_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "availability": self.availability.value,
            "affordability": self.affordability,
            "expected_reserve_gain": self.expected_reserve_gain,
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
        }


@dataclass(frozen=True, slots=True)
class ResourceEconomyState:
    """Normalized reserve and renewal evidence at one decision boundary."""

    reserve_satisfaction: float
    acquisition_resource_available: bool
    options: tuple[ResourceRenewalOption, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reserve_satisfaction",
            _unit(self.reserve_satisfaction, subject="reserve satisfaction"),
        )
        if not isinstance(self.acquisition_resource_available, bool):
            raise ResourceEconomyError(
                "acquisition resource availability must be boolean"
            )
        if not isinstance(self.options, tuple) or any(
            not isinstance(item, ResourceRenewalOption) for item in self.options
        ):
            raise ResourceEconomyError("resource renewal options must be typed")
        kinds = tuple(item.kind for item in self.options)
        if len(kinds) != len(set(kinds)):
            raise ResourceEconomyError("resource renewal kinds cannot be duplicated")
        if set(kinds) != set(ResourceRenewalKind):
            raise ResourceEconomyError(
                "resource renewal evidence must classify every renewal kind"
            )

    @property
    def available_renewals(self) -> tuple[ResourceRenewalKind, ...]:
        return tuple(
            item.kind
            for item in self.options
            if item.availability is GoalAvailability.AVAILABLE
        )

    @property
    def unknown_renewals(self) -> tuple[ResourceRenewalKind, ...]:
        return tuple(
            item.kind
            for item in self.options
            if item.availability is GoalAvailability.UNKNOWN
        )

    @property
    def hard_blocked(self) -> bool:
        return (
            not self.acquisition_resource_available
            and not self.available_renewals
            and not self.unknown_renewals
        )

    def collection_decision(
        self,
        *,
        acquisition_binding_available: bool,
    ) -> CollectionResourceDecision:
        if not isinstance(acquisition_binding_available, bool):
            raise TypeError("acquisition binding availability must be boolean")
        if self.acquisition_resource_available and acquisition_binding_available:
            return CollectionResourceDecision.ACQUIRE
        if self.available_renewals:
            return CollectionResourceDecision.REPLENISH
        if self.unknown_renewals:
            return CollectionResourceDecision.INVESTIGATE
        return CollectionResourceDecision.BLOCKED

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.resource-economy.v1",
            "reserve_satisfaction": self.reserve_satisfaction,
            "acquisition_resource_available": self.acquisition_resource_available,
            "renewal_options": [item.public_dict() for item in self.options],
            "available_renewals": [item.value for item in self.available_renewals],
            "unknown_renewals": [item.value for item in self.unknown_renewals],
            "hard_blocked": self.hard_blocked,
            "raw_currency_included": False,
            "title_item_identity_included": False,
        }


def _unit(value: object, *, subject: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ResourceEconomyError(f"{subject} must be between zero and one")
    return float(value)


__all__ = [
    "CollectionResourceDecision",
    "ResourceEconomyError",
    "ResourceEconomyState",
    "ResourceRenewalKind",
    "ResourceRenewalOption",
]
