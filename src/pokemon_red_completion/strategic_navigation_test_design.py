"""ROM-free capability audit for a sealed strategic-navigation partition.

The audit deliberately stops before route planning.  It can show whether a
public scenario specification places the player near a non-teacher objective,
which makes a cheapest-route disagreement plausible.  It cannot claim that a
disagreement was measured; that requires the still-sealed cartridge context.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pokemon_red_completion.quest import QuestGraph
from pokemon_red_completion.strategic_navigation_scenarios import (
    StrategicNavigationScenarioRegistry,
)

STRATEGIC_SEALED_TEST_MINIMUM_CHALLENGE_HYPOTHESES = 6


@dataclass(frozen=True, slots=True)
class StrategicSealedTestCaseDesign:
    scenario_id: str
    declared_challenge_hypothesis: bool
    structurally_challenge_eligible: bool
    local_non_teacher_objective_ids: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "declared_challenge_hypothesis": self.declared_challenge_hypothesis,
            "structurally_challenge_eligible": self.structurally_challenge_eligible,
            "local_non_teacher_objective_ids": list(
                self.local_non_teacher_objective_ids
            ),
        }


@dataclass(frozen=True, slots=True)
class StrategicSealedTestDesignAudit:
    cases: tuple[StrategicSealedTestCaseDesign, ...]
    minimum_challenge_hypotheses: int

    @property
    def declared_challenge_hypotheses(self) -> int:
        return sum(case.declared_challenge_hypothesis for case in self.cases)

    @property
    def structurally_challenge_eligible(self) -> int:
        return sum(case.structurally_challenge_eligible for case in self.cases)

    @property
    def current_design_admitted(self) -> bool:
        return (
            self.declared_challenge_hypotheses >= self.minimum_challenge_hypotheses
            and all(
                not case.declared_challenge_hypothesis
                or case.structurally_challenge_eligible
                for case in self.cases
            )
        )

    def public_dict(self) -> dict[str, object]:
        declared = self.declared_challenge_hypotheses
        eligible = self.structurally_challenge_eligible
        return {
            "schema": "strategic-sealed-test-design-audit-v1",
            "test_scenarios": len(self.cases),
            "minimum_challenge_hypotheses": self.minimum_challenge_hypotheses,
            "declared_challenge_hypotheses": declared,
            "structurally_challenge_eligible": eligible,
            "declared_challenge_best_case_two_sided_exact_p": (
                _perfect_scorer_two_sided_exact_p(declared)
            ),
            "eligible_repair_best_case_two_sided_exact_p": (
                _perfect_scorer_two_sided_exact_p(eligible)
            ),
            "current_design_admitted": self.current_design_admitted,
            "structural_eligibility_is_measured_disagreement": False,
            "cases": [case.public_dict() for case in self.cases],
        }


def audit_strategic_sealed_test_design(
    registry: StrategicNavigationScenarioRegistry,
    graph: QuestGraph,
) -> StrategicSealedTestDesignAudit:
    """Inspect only committed test specifications, never captures or routes."""

    if not isinstance(registry, StrategicNavigationScenarioRegistry):
        raise TypeError("registry must be a StrategicNavigationScenarioRegistry")
    if not isinstance(graph, QuestGraph):
        raise TypeError("graph must be a QuestGraph")
    cases = []
    for scenario in registry.scenarios:
        if scenario.partition != "test":
            continue
        completed_regions = {
            graph.objective(objective_id).target_region
            for objective_id in scenario.completed_objective_ids
        }
        local_non_teacher = tuple(
            objective_id
            for objective_id in scenario.candidate_objective_ids
            if objective_id != scenario.teacher_objective_id
            and graph.objective(objective_id).target_region in completed_regions
        )
        cases.append(
            StrategicSealedTestCaseDesign(
                scenario_id=scenario.scenario_id,
                declared_challenge_hypothesis=(
                    scenario.cost_baseline_challenge_hypothesis
                ),
                structurally_challenge_eligible=bool(local_non_teacher),
                local_non_teacher_objective_ids=local_non_teacher,
            )
        )
    if not cases:
        raise ValueError("strategic registry has no sealed test scenarios")
    return StrategicSealedTestDesignAudit(
        cases=tuple(cases),
        minimum_challenge_hypotheses=(
            STRATEGIC_SEALED_TEST_MINIMUM_CHALLENGE_HYPOTHESES
        ),
    )


def _perfect_scorer_two_sided_exact_p(disagreements: int) -> float:
    if disagreements < 1:
        return 1.0
    return min(1.0, 2.0 * math.pow(0.5, disagreements))
