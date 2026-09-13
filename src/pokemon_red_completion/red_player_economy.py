"""Opt-in cash evidence and supply-derived budgets for native player choices.

Item identities belong to private evidence only. Policy context carries cash and
the independently reconstructed useful budget, never the full inventory.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .goal_manager import GoalKind
from .provenance import canonical_sha256
from .red_capture_funding_budget import RedCaptureFundingBudget
from .red_goal_context_profile import RedGoalContextProfile
from .red_goal_skills import _CAPTURE_ITEMS
from .resource_economy_observation import ECONOMY_SCHEMA, EconomySnapshot

ECONOMY_CONTEXT_EVENT = "red_player_economy_context"
ECONOMY_CONTEXT_SCHEMA = "pokemon.red.player-economy-context.v1"
ECONOMY_TRAINING_EVENT_SCHEMA = "pokemon.red.registered-player-training-outcome.v2"
SUPPLY_FIELDS = ("economy_reserve_target", "economy_purchase_limit",
                 "economy_item_id", "economy_unit_price")


@dataclass(frozen=True, slots=True)
class PlayerEconomySupply:
    reserve_target: int
    purchase_limit: int
    item_id: int
    unit_price: int

    def __post_init__(self) -> None:
        if any(type(getattr(self, key)) is not int for key in self.__dataclass_fields__):
            raise ValueError("economy supply fields must be integers")
        if (self.reserve_target < 0 or not 1 <= self.purchase_limit <= 99
                or self.item_id not in _CAPTURE_ITEMS or self.unit_price <= 0):
            raise ValueError("economy supply contract differs")

    def plan_fields(self) -> dict[str, int]:
        return dict(zip(SUPPLY_FIELDS, (self.reserve_target, self.purchase_limit,
                                       self.item_id, self.unit_price), strict=True))

    @classmethod
    def from_plan(cls, document: Mapping[str, object]) -> "PlayerEconomySupply":
        values = [document.get(key) for key in SUPPLY_FIELDS]
        if any(type(value) is not int for value in values):
            raise ValueError("economy supply declaration differs")
        return cls(*values)  # type: ignore[arg-type]

    def budget(self, snapshot: EconomySnapshot | None, observed_count: object
               ) -> RedCaptureFundingBudget | None:
        if snapshot is None:
            return None
        bag = _red_bag(snapshot)
        count = sum(n for item, n in bag.items() if item in _CAPTURE_ITEMS)
        if type(observed_count) is not int or observed_count != count:
            raise ValueError("economy capture count differs from bag evidence")
        stock = bag.get(self.item_id, 0)
        if stock == 0 and len(bag) >= 20:
            return None
        return RedCaptureFundingBudget(snapshot.cash, count, self.reserve_target,
                                       self.purchase_limit, stock, self.unit_price)


def supply_from_profile(profile: RedGoalContextProfile) -> PlayerEconomySupply:
    """Use the existing bound shop contract, not an arbitrary cash target."""
    providers = [spec for spec in profile.providers if spec.kind is GoalKind.RESUPPLY]
    if len(providers) != 1:
        raise ValueError("economy training requires one capture supply provider")
    parameters = providers[0].parameters
    purchases = parameters.get("purchases")
    if (parameters.get("affordable_ball_purchase") is not True
            or not isinstance(purchases, (list, tuple)) or len(purchases) != 1
            or not isinstance(purchases[0], Mapping)):
        raise ValueError("economy training requires a bounded capture purchase")
    row = purchases[0]
    return PlayerEconomySupply.from_plan({
        "economy_reserve_target": profile.manager_config.desired_capture_items,
        "economy_purchase_limit": row.get("quantity"),
        "economy_item_id": row.get("item_id"), "economy_unit_price": row.get("unit_price"),
    })


def _red_bag(snapshot: EconomySnapshot) -> dict[int, int]:
    if snapshot.cash > 999999 or len(snapshot.inventory) > 20:
        raise ValueError("Red economy bounds differ")
    bag = {}
    for key, count in snapshot.inventory:
        if re.fullmatch(r"red-item-[0-9]{3}", key) is None:
            raise ValueError("Red economy item identity differs")
        item = int(key[-3:])
        if not 1 <= item <= 255 or not 1 <= count <= 99:
            raise ValueError("Red economy inventory bounds differ")
        bag[item] = count
    return bag


def snapshot_document(snapshot: EconomySnapshot | None) -> dict[str, object] | None:
    if snapshot is None:
        return None
    _red_bag(snapshot)
    return {"schema": ECONOMY_SCHEMA, "cash": snapshot.cash,
            "inventory": [list(entry) for entry in snapshot.inventory]}


def restore_snapshot(value: object) -> EconomySnapshot | None:
    if value is None:
        return None
    if (not isinstance(value, Mapping) or set(value) != {"schema", "cash", "inventory"}
            or value.get("schema") != ECONOMY_SCHEMA or type(value.get("cash")) is not int
            or not isinstance(value.get("inventory"), list)):
        raise ValueError("economy snapshot document differs")
    entries = []
    for entry in value["inventory"]:
        if (not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str)
                or type(entry[1]) is not int):
            raise ValueError("economy inventory document differs")
        entries.append((entry[0], entry[1]))
    snapshot = EconomySnapshot(value["cash"], tuple(entries))
    _red_bag(snapshot)
    return snapshot


def restore_context(value: Mapping[str, object], supply: PlayerEconomySupply
                    ) -> tuple[EconomySnapshot | None, RedCaptureFundingBudget | None]:
    """Reconstruct the budget; never accept a free cash target from a journal."""
    before = value.get("before")
    if not isinstance(before, Mapping):
        raise ValueError("economy context lacks an observation")
    snapshot = restore_snapshot(value.get("economy_before"))
    budget = supply.budget(snapshot, semantic_facts(before).get("capture_item_count"))
    if canonical_sha256(value.get("budget")) != canonical_sha256(
        budget.public_dict() if budget is not None else None,
    ):
        raise ValueError("economy budget differs from observed supplies")
    return snapshot, budget


def semantic_facts(before: Mapping[str, object]) -> Mapping[str, object]:
    semantic = before.get("semantic_observation")
    if (before.get("schema") != "pokemon.red.registered-goal-observation.v1"
            or not isinstance(semantic, Mapping)):
        raise ValueError("economy learning requires registered semantic observations")
    return semantic
