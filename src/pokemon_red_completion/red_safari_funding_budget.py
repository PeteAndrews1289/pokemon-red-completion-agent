"""Derive a prospective cash target from an eligible paid Safari entry.

This is a single admission budget, not proof the entrance is reachable or that
sufficient funds can be earned. Quotes must be retained with the decision.
Only legitimate non-money prerequisites qualify this funding demand.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from . import red_live_safari
from .observation import PokemonRedStateReader
from .red_safari_acquisition import SAFARI_ADMISSION_COST
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

discover_eligible_red_safari_areas = red_live_safari.discover_eligible_red_safari_areas
_is_valid_player_money = red_live_safari._is_valid_player_money


@dataclass(frozen=True, slots=True)
class RedSafariFundingBudget:
    available_funds: int
    admission_cost: int = SAFARI_ADMISSION_COST

    def __post_init__(self) -> None:
        if (
            type(self.available_funds) is not int
            or isinstance(self.available_funds, bool)
            or self.available_funds < 0
            or self.available_funds > 999_999
        ):
            raise ValueError("available funds must be an observed nonnegative integer <= 999999")
        if (
            type(self.admission_cost) is not int
            or isinstance(self.admission_cost, bool)
            or self.admission_cost != SAFARI_ADMISSION_COST
        ):
            raise ValueError("admission cost must equal SAFARI_ADMISSION_COST")

    @property
    def available_cash(self) -> int:
        return self.available_funds

    @property
    def cost(self) -> int:
        return self.admission_cost

    @property
    def target_cash(self) -> int:
        return self.admission_cost

    @property
    def shortfall(self) -> int:
        return max(0, self.admission_cost - self.available_funds)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.safari-funding-budget.v1",
            "available_funds": self.available_funds,
            "admission_cost": self.admission_cost,
            "cost": self.cost,
            "shortfall": self.shortfall,
            "target_cash": self.target_cash,
        }


RedSafariFundingQuote = RedSafariFundingBudget


def red_safari_funding_budget(
    rom: bytes,
    registered_species_numbers: Collection[int],
    *,
    free_storage_slots: int,
    world: StrategicScenarioRouteWorld,
    reader: PokemonRedStateReader,
) -> RedSafariFundingBudget | None:
    """Quote one paid Safari entry if non-money eligibility is satisfied."""

    if not isinstance(rom, bytes):
        return None
    raw = reader.read()
    if not red_live_safari._is_valid_player_money(raw.player_money):
        return None
    areas = red_live_safari.discover_eligible_red_safari_areas(
        rom,
        registered_species_numbers,
        free_storage_slots=free_storage_slots,
        world=world,
        reader=reader,
    )
    if not areas:
        return None
    return RedSafariFundingBudget(available_funds=raw.player_money)


quote_red_safari_funding = red_safari_funding_budget

__all__ = [
    "RedSafariFundingBudget",
    "RedSafariFundingQuote",
    "quote_red_safari_funding",
    "red_safari_funding_budget",
]
