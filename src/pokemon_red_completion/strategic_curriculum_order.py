"""Static audit of exact scenario frontiers against qualified teacher order.

The quest graph describes what the game permits.  A qualified chapter skill can
have a narrower input boundary because it was demonstrated in one particular
teacher order.  This module keeps those two claims separate: it reports when a
scenario contains an objective whose *current qualified skill* requires another
objective that the exact scenario deliberately leaves incomplete.

An incompatibility is a curriculum coverage gap, not proof that the cartridge
state is impossible.  A different bounded skill may legitimately teach the same
objective in another order.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.strategic_navigation_scenarios import (
    StrategicNavigationScenarioRegistry,
)


@dataclass(frozen=True, slots=True)
class QualifiedSkillOrderContract:
    """Objective prerequisites imposed by the currently qualified teacher skill."""

    objective_id: str
    required_objective_ids: frozenset[str]
    reason: str
    when_objective_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        known = frozenset(item.id for item in COMPLETION_QUEST)
        if self.objective_id not in known:
            raise ValueError("qualified skill contract objective is unknown")
        if (
            not self.required_objective_ids
            or self.objective_id in self.required_objective_ids
            or not self.required_objective_ids.issubset(known)
            or not self.when_objective_ids.issubset(known)
        ):
            raise ValueError("qualified skill contract prerequisites are invalid")
        if not self.reason:
            raise ValueError("qualified skill contract reason must be non-empty")


# Only constraints stricter than, or operationally important beyond, the public
# quest graph belong here.  For example, Strength's quest prerequisite is merely
# reaching Fuchsia, but the qualified Warden skill needs Gold Teeth supplied by
# the currently qualified Safari/Surf chapter. Koga likewise consumes the
# Surf-ready party/move boundary established by the later-order teacher run.
RED_QUALIFIED_SKILL_ORDER_CONTRACTS = (
    QualifiedSkillOrderContract(
        objective_id="defeat_koga",
        required_objective_ids=frozenset({"reach_fuchsia", "obtain_surf"}),
        reason="The qualified Koga chapter starts at the Surf-ready Fuchsia boundary.",
    ),
    QualifiedSkillOrderContract(
        objective_id="obtain_strength",
        required_objective_ids=frozenset({"reach_fuchsia", "obtain_surf"}),
        reason=(
            "The qualified Strength chapter requires Gold Teeth supplied by the "
            "current Safari/Surf chapter."
        ),
    ),
    QualifiedSkillOrderContract(
        objective_id="reach_cinnabar",
        required_objective_ids=frozenset({"obtain_surf", "defeat_sabrina"}),
        reason=(
            "The qualified Cinnabar chapter starts from the post-Sabrina Saffron "
            "boundary and uses that route's Fly preparation."
        ),
    ),
)


def audit_qualified_skill_order(
    registry: StrategicNavigationScenarioRegistry,
    *,
    contracts: tuple[QualifiedSkillOrderContract, ...] = (RED_QUALIFIED_SKILL_ORDER_CONTRACTS),
) -> dict[str, object]:
    """Report exact frontiers incompatible with the current teacher order.

    The result contains registry identities only.  It does not inspect a ROM,
    private capture, test scenario payload, or live skill availability.
    """

    if not isinstance(registry, StrategicNavigationScenarioRegistry):
        raise TypeError("registry must be a strategic scenario registry")
    if len({item.objective_id for item in contracts}) != len(contracts):
        raise ValueError("qualified skill order contracts contain a duplicate")

    contract_by_objective = {item.objective_id: item for item in contracts}
    incompatible = []
    for scenario in registry.learning_scenarios():
        completed = frozenset(scenario.completed_objective_ids)
        blockers = []
        for objective_id in sorted(completed.intersection(contract_by_objective)):
            contract = contract_by_objective[objective_id]
            if not contract.when_objective_ids.issubset(completed):
                continue
            missing = sorted(contract.required_objective_ids.difference(completed))
            if not missing:
                continue
            blockers.append(
                {
                    "objective_id": objective_id,
                    "required_but_absent_objective_ids": missing,
                    "reason": contract.reason,
                }
            )
        if blockers:
            incompatible.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "partition": scenario.partition,
                    "current_qualified_skill_blockers": blockers,
                }
            )

    return {
        "schema": "strategic-curriculum-order-audit-v1",
        "claim": (
            "These are current qualified-teacher order gaps, not impossible cartridge states."
        ),
        "qualified_skill_contract_count": len(contracts),
        "learning_scenarios_checked": len(registry.learning_scenarios()),
        "incompatible_learning_scenario_count": len(incompatible),
        "incompatible_learning_scenarios": incompatible,
        "test_scenarios_opened": 0,
        "live_skill_availability_checked": False,
        "private_captures_opened": 0,
    }
