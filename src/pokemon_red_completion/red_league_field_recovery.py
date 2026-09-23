"""Explicit campaign-wide owned-item recovery, never free League supplies.

The same action/frame-limited executor serves recovery and the next battle.
Replacement valuation is separate from observed cash, and not a purchase claim.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport
from .living_dex_option_value import LivingDexOptionValueModel
from .observation import ItemId
from .red_autonomous_player import _record
from .red_faint_recovery import RedFaintAwareFieldRestoreGoalProvider
from .red_recovery_intermission import run_recovery_intermission

# Red data/items/prices.asm buy prices, not sell prices. Only supported field items.
_REPLACEMENT_PRICES = {
    ItemId.POTION: 300,
    ItemId.SUPER_POTION: 700,
    ItemId.HYPER_POTION: 1500,
    ItemId.FULL_RESTORE: 3000,
    ItemId.FULL_HEAL: 600,
    ItemId.REVIVE: 1500,
}


@dataclass
class LeagueFieldRecovery:
    """One explicitly configured campaign; failures permanently close this object."""

    model: LivingDexOptionValueModel
    model_sha256: str
    output: Path
    snapshot: Callable[[], bytes]
    target_cash: int
    maximum_items: int = 6
    seed: int = 0
    consumed: Counter[int] = field(default_factory=Counter, init=False)
    boundaries: int = field(default=0, init=False)
    failed: bool = field(default=False, init=False)
    claimed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.model, LivingDexOptionValueModel)
            or self.model.model_sha256 != self.model_sha256
            or not isinstance(self.output, Path)
            or not callable(self.snapshot)
            or type(self.maximum_items) is not int
            or not 1 <= self.maximum_items <= 12
            or type(self.seed) is not int
            or self.seed < 0
            or type(self.target_cash) is not int
            or not 0 <= self.target_cash <= 999999
        ):
            raise ValueError("invalid explicit League field recovery configuration")

    def claim(self) -> None:
        if self.claimed or self.failed:
            raise ValueError("League recovery campaign already claimed")
        self.output.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.claimed = True
        _record(self.output / "campaign.json", {
            "model_sha256": self.model_sha256, "target_cash": self.target_cash,
            "maximum_items": self.maximum_items, "seed": self.seed,
            "replacement_prices": {str(int(k)):v for k,v in _REPLACEMENT_PRICES.items()},
            "replacement_value_is_cash_spent": False,
        })

    @property
    def replacement_cost(self) -> int:
        return sum(
            _REPLACEMENT_PRICES[ItemId(item)] * count for item, count in self.consumed.items()
        )

    def _accept(self, report: object) -> None:
        if not isinstance(report, GoalExecutionReport):
            raise ValueError("recovery receipt has wrong type")
        item = report.evidence.get("item_id")
        if (
            type(item) is not int
            or item not in _REPLACEMENT_PRICES
            or report.evidence.get("owned_items_consumed") != 1
            or sum(self.consumed.values()) >= self.maximum_items
        ):
            raise ValueError("recovery consumption exceeds declared campaign")
        self.consumed[item] += 1

    def choose(
        self, recovery: RedFaintAwareFieldRestoreGoalProvider, next_goal: Callable
    ) -> ExecutableGoalBinding:
        if not self.claimed or self.failed:
            raise ValueError("League recovery campaign is not active")
        ordinal = self.boundaries
        self.boundaries += 1
        try:
            return run_recovery_intermission(
                model=self.model,
                model_sha256=self.model_sha256,
                output=self.output / f"boundary-{ordinal:02d}",
                recovery=recovery,
                next_goal=next_goal,
                snapshot=self.snapshot,
                target_cash=self.target_cash,
                seed=self.seed + ordinal * 16,
                maximum_items=self.maximum_items - sum(self.consumed.values()),
                on_verified_recovery=self._accept,
            )
        except BaseException:
            self.failed = True
            raise

    def expected_bag(
        self, supplied: tuple[tuple[int, int], ...], battle_full_restores: int
    ) -> tuple[tuple[int, int], ...]:
        if type(battle_full_restores) is not int or battle_full_restores < 0:
            raise ValueError("invalid battle recovery consumption")
        spent = self.consumed.copy()
        spent[int(ItemId.FULL_RESTORE)] += battle_full_restores
        available = dict(supplied)
        if any(count > available.get(item, 0) for item, count in spent.items()):
            raise ValueError("campaign consumption exceeds owned inventory")
        return tuple(
            (item, remaining) for item, count in supplied if (remaining := count - spent[item]) > 0
        )
