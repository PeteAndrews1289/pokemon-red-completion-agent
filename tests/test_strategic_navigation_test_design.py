from pathlib import Path

from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)
from pokemon_red_completion.strategic_navigation_test_design import (
    audit_strategic_sealed_test_design,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_current_sealed_design_is_blocked_before_private_evidence_is_opened() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)

    audit = audit_strategic_sealed_test_design(registry, COMPLETION_QUEST)

    assert len(audit.cases) == 12
    assert audit.minimum_challenge_hypotheses == 6
    assert audit.declared_challenge_hypotheses == 0
    assert audit.structurally_challenge_eligible == 10
    assert audit.current_design_admitted is False
    assert audit.public_dict()["declared_challenge_best_case_two_sided_exact_p"] == 1.0
    assert audit.public_dict()["eligible_repair_best_case_two_sided_exact_p"] == (
        0.001953125
    )


def test_structural_audit_does_not_claim_measured_route_disagreement() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)

    payload = audit_strategic_sealed_test_design(
        registry, COMPLETION_QUEST
    ).public_dict()

    assert payload["structural_eligibility_is_measured_disagreement"] is False
    cases = payload["cases"]
    assert isinstance(cases, list)
    assert all("route_cost" not in case for case in cases)
