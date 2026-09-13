"""Prospective economy learning integration for Pokemon Red.

Bridges title-specific Red resource/quote observations with the shared
living-Dex option-value learner. Earning opportunities remain GoalKind.RESUPPLY
with positive conditional income quotes. Safety gates (recovery, critical party,
storage) remain deterministic and non-bypassable.

CRITICAL HONEST BOUNDARY:
- The nine legacy targets remain unchanged. Feature-v4 fitting can learn a
  separate masked liquidity-gain/cash-loss head from measured EconomyOutcome
  evidence and contribute its predictions to existing goal utility.
- This prospective bridge does NOT claim to be an operational income learner yet.
- Live activation remains strictly off; no mapping of cash gain to completion_gain
  or dependency_unlock_gain.
- Runtime/journal activation remains the next slice; synthetic objective tests
  are not evidence of an actual Red income fit.
- declared_useful_supply_budget is a prospective budget helper, NOT runtime
  authority (runtime budgets are independently derived in red_capture_funding_budget.py).
- Explicit shortfall * income interaction is retained in economy_features because
  a linear regression model cannot synthesize that interaction product itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from pokemon_red_completion.goal_manager import GoalKind, GoalOpportunity
from pokemon_red_completion.living_dex_goal_policy import (
    economy_offer_from_opportunity,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexObservedOutcome,
    LivingDexOutcomeStatus,
    upgrade_option_value_model_for_economy,
)
from pokemon_red_completion.red_registered_outcome import (
    red_registered_outcome_from_observations,
)
from pokemon_red_completion.resource_economy_observation import (
    ECONOMY_FEATURE_NAMES,
    EconomyMode,
    EconomyOffer,
    EconomyOutcome,
    EconomySnapshot,
    economy_features,
    economy_outcome,
)


def _count(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def declared_useful_supply_budget(
    unmet_balls: int = 0,
    unmet_potions: int = 0,
    ball_price: int = 200,
    potion_price: int = 300,
    *,
    minimum_reserve: int = 0,
) -> int:
    """Derive target cash from declared supply quantities.

    This is a helper for unit testing and prospective feature scaling,
    NOT runtime authority.
    """
    _count(unmet_balls, "unmet balls")
    _count(unmet_potions, "unmet potions")
    _count(ball_price, "ball price")
    _count(potion_price, "potion price")
    _count(minimum_reserve, "minimum reserve")
    return unmet_balls * ball_price + unmet_potions * potion_price + minimum_reserve


def is_earning_opportunity(opportunity: GoalOpportunity) -> bool:
    """True iff this opportunity provides an explicit positive income quote."""
    if not isinstance(opportunity, GoalOpportunity):
        raise TypeError("opportunity must be a GoalOpportunity")
    return (
        opportunity.resource_quote is not None
        and opportunity.resource_quote.expected_income > 0
    )


def is_purchase_opportunity(opportunity: GoalOpportunity) -> bool:
    """True iff this opportunity provides an explicit positive purchase quote."""
    if not isinstance(opportunity, GoalOpportunity):
        raise TypeError("opportunity must be a GoalOpportunity")
    return (
        opportunity.resource_quote is not None
        and opportunity.resource_quote.purchase_cost > 0
    )


def red_registered_economy_outcome(
    before: Mapping[str, object],
    after: Mapping[str, object],
    *,
    selected_kind: GoalKind,
    succeeded: bool,
    actions: int,
    frames: int,
    maximum_actions: int,
    maximum_frames: int,
    before_economy: EconomySnapshot | None = None,
    after_economy: EconomySnapshot | None = None,
    target_cash: int,
    interrupted: bool = False,
) -> LivingDexObservedOutcome:
    """Link registered outcome reconstruction with computed economy observations.

    - If interrupted: returns censored outcome with censor_reason=EXTERNAL_INTERRUPTION
      and no targets.
    - If before_economy or after_economy is missing: censors with OBSERVATION_FAILED,
      never returning an apparently successful legacy outcome pretending to be an economy example.
    - Quoted success cannot fabricate cash: liquidity gain is strictly bounded by
      observed positive cash change and unmet before-budget.
    - Actual losses on failure are retained (settled failure records cash_loss).
    - No censored outcome retains economy targets.
    """
    _count(target_cash, "target cash")
    if interrupted:
        return LivingDexObservedOutcome(
            status=LivingDexOutcomeStatus.CENSORED,
            censor_reason=LivingDexCensorReason.EXTERNAL_INTERRUPTION,
            economy=None,
        )
    if before_economy is None or after_economy is None:
        return LivingDexObservedOutcome(
            status=LivingDexOutcomeStatus.CENSORED,
            censor_reason=LivingDexCensorReason.OBSERVATION_FAILED,
            economy=None,
        )
    base_outcome = red_registered_outcome_from_observations(
        before,
        after,
        selected_kind=selected_kind,
        succeeded=succeeded,
        actions=actions,
        frames=frames,
        maximum_actions=maximum_actions,
        maximum_frames=maximum_frames,
    )
    if base_outcome.status is LivingDexOutcomeStatus.CENSORED:
        return base_outcome
    econ = economy_outcome(
        before_economy,
        after_economy,
        target_cash=target_cash,
        interrupted=False,
    )
    return replace(base_outcome, economy=econ)


__all__ = [
    "ECONOMY_FEATURE_NAMES",
    "EconomyMode",
    "EconomyOffer",
    "EconomyOutcome",
    "EconomySnapshot",
    "declared_useful_supply_budget",
    "economy_features",
    "economy_offer_from_opportunity",
    "economy_outcome",
    "is_earning_opportunity",
    "is_purchase_opportunity",
    "red_registered_economy_outcome",
    "upgrade_option_value_model_for_economy",
]
