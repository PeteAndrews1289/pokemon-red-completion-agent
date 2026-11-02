"""Explicit campaign-wide owned-item recovery, never free League supplies.

The same action/frame-limited executor serves recovery and the next battle.
Replacement valuation is separate from observed cash, and not a purchase claim.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from .goal_manager import GoalKind, GoalUnavailableReason
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .living_dex_option_value import LivingDexOptionValueModel
from .observation import ItemId
from .player_readiness import PlayerReadiness
from .red_autonomous_player import _record
from .red_faint_recovery import RedFaintAwareFieldRestoreGoalProvider, plan_faint_aware_recovery
from .red_goal_manager import RedGoalBindingOffer
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
    observe_readiness: Callable[[], PlayerReadiness] | None = None
    selection_mode: str = 'model'
    conserve_owned_medicine: bool = False
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
            or (self.observe_readiness is not None and not callable(self.observe_readiness))
            or type(self.selection_mode) is not str
            or self.selection_mode not in {'model', 'deterministic_safety'}
            or type(self.conserve_owned_medicine) is not bool
            or self.conserve_owned_medicine and self.selection_mode != 'deterministic_safety'
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
            "observed_readiness_enabled": self.observe_readiness is not None,
            "conserve_owned_medicine": self.conserve_owned_medicine,
            **({'heal_below_fraction': 0.75, 'prioritize_status_cure': True}
               if self.conserve_owned_medicine else {}),
            **({'selection_mode': self.selection_mode, 'learned_medicine': False,
                'model_queries': 0} if self.selection_mode != 'model' else {}),
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
            if self.selection_mode == 'deterministic_safety':
                return self._supported_choose(recovery, next_goal, ordinal)
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
                observe_readiness=self.observe_readiness,
            )
        except BaseException:
            self.failed = True
            raise

    def _supported_offer(self, recovery, observation):
        if not self.conserve_owned_medicine:
            return recovery.offer(observation)
        raw = observation.raw
        # Retain the existing complete living-party/inventory validation before
        # narrowing recipients. This never invents HP, items or readiness.
        plan_faint_aware_recovery(raw, allowed_items=recovery.allowed_items,
            eligible_party_indices=recovery.eligible_party_indices,
            prioritize_status_cure=recovery.prioritize_status_cure)
        eligible = frozenset(
            i for i, (hp, maximum, status) in enumerate(zip(
                raw.party_hp, raw.party_max_hp, raw.party_status, strict=True))
            if (status or hp * 4 < maximum * 3)
            and (recovery.eligible_party_indices is None or i in recovery.eligible_party_indices)
        )
        if not eligible:
            return RedGoalBindingOffer.unavailable(
                GoalKind.RESTORE_TEAM, GoalUnavailableReason.NO_LEGAL_TARGET)
        return replace(recovery, eligible_party_indices=eligible,
            prioritize_status_cure=True).offer(observation)

    def _supported_choose(self, recovery, next_goal, ordinal):
        """Reuse one-owned-item mechanics as disclosed support, never a learned choice."""
        output = self.output / f'boundary-{ordinal:02d}'
        output.mkdir(mode=0o700, exist_ok=False)
        step = 0
        while True:
            state = self.snapshot()
            observation = recovery.adapter.observe()
            if (not observation.input_ready or observation.raw.battle_state
                    or recovery.emulator.pressed_buttons):
                raise ValueError('Supported income recovery requires released field control')
            offer = self._supported_offer(recovery, observation)
            if self.snapshot() != state:
                raise ValueError('Supported recovery enumeration changed the native state')
            if offer.binding is None:
                if offer.unavailable_reason not in {
                    GoalUnavailableReason.NO_LEGAL_TARGET, GoalUnavailableReason.MISSING_RESOURCE,
                }:
                    raise ValueError('Supported income recovery lost its native boundary')
                binding = next_goal(observation)
                if (not isinstance(binding, ExecutableGoalBinding)
                        or binding.kind in {GoalKind.RESTORE_TEAM, GoalKind.RECOVER_CONTROL}
                        or self.snapshot() != state):
                    raise ValueError('Supported income has no verified next battle')
                return binding
            if sum(self.consumed.values()) >= self.maximum_items:
                raise ValueError('Supported recovery item budget exhausted')
            report = offer.binding.execute()
            if offer.binding.verify(report) != GoalVerification.succeeded():
                raise ValueError('Supported income medicine failed exact verification')
            self._accept(report)
            _record(output / f'item-{step:02d}.json', {
                'selection_mode': 'deterministic_safety', 'model_queries': 0,
                'learned_medicine': False, 'evidence': dict(report.evidence),
                'actions': report.actions_executed, 'frames': report.frames_executed,
            })
            step += 1

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
