"""Semantic post-battle preparation requests; disclosed rule, not learned strategy."""

from dataclasses import dataclass

from .party import StatusCondition
from .party_preparation import (
    ObservedOpponent,
    PreparationBudget,
    PreparationPlan,
    build_preparation_plan,
)


@dataclass(frozen=True)
class StoryPreparationReview:
    plan: PreparationPlan
    next_action: str

    def public_dict(self):
        return {
            "schema": "pokemon.story-preparation-review.v1",
            "learned_preparation": False,
            "next_action": self.next_action,
            "opposition_level": self.plan.opposition_level,
            "observed_opponents": self.plan.observed_opponents,
            "targets": dict(self.plan.targets),
            "reason": self.plan.reason,
        }


def review_story_preparation(members, episode, *, encounter_ref, field_ready, budget=None):
    """Review the latest encounter, counting each actually seen opponent once.

    Conflicting or missing roster position evidence is not guessed. This function
    never sends inputs, selects attacks, starts grinding or resets attempt costs.
    """
    if type(field_ready) is not bool:
        raise ValueError("field readiness must be explicit")
    opponents = {}
    roster_count = None
    for decision in episode["decisions"]:
        battle = decision["observation"]["features"]["battle"]
        if not battle.get("active") or battle.get("kind") != "trainer":
            continue
        count = battle.get("opponent_party_count")
        remaining = battle.get("opponent_remaining_count")
        level = battle.get("opponent_level")
        if type(count) is not int or type(remaining) is not int or not 1 <= remaining <= count <= 6:
            raise ValueError("story preparation lacks observed opponent position")
        if roster_count is not None and roster_count != count:
            raise ValueError("conflicting observed story roster size")
        roster_count = count
        opponent = ObservedOpponent(encounter_ref, count - remaining + 1, level)
        if opponent.position in opponents and opponents[opponent.position] != opponent:
            raise ValueError("conflicting observed story opponent")
        opponents[opponent.position] = opponent
    plan = build_preparation_plan(
        members, tuple(opponents.values()), budget=budget or PreparationBudget()
    )
    if not field_ready:
        action = "settle_battle"
    elif any(
        m.observation.is_fainted
        or m.observation.status != StatusCondition.HEALTHY
        or m.observation.hp_ratio < 0.5
        or m.observation.total_pp <= 2
        for m in members
    ):
        action = "recover"
    elif not opponents:
        action = "need_opposition_evidence"
    elif plan.targets:
        action = "prepare_party"
    else:
        action = "continue_story"
    return StoryPreparationReview(plan, action)


def require_preparation_targets(members, targets):
    """Keep an active request's targets fixed; completion never refills budgets."""
    live = {m.specimen_ref: m.observation for m in members}
    if any(type(target) is not int or not 1 <= target <= 100 for target in targets.values()):
        raise ValueError("invalid preparation target")
    if any(ref not in live for ref in targets):
        raise ValueError("preparation roster changed; reassessment required")
    if any(live[ref].level < target for ref, target in targets.items()):
        raise ValueError("automatic party preparation required before next story battle")
