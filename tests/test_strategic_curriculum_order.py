from __future__ import annotations

from pathlib import Path

import pytest

from pokemon_red_completion.strategic_curriculum_order import (
    QualifiedSkillOrderContract,
    audit_qualified_skill_order,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _by_id(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    scenarios = payload["incompatible_learning_scenarios"]
    assert isinstance(scenarios, list)
    return {str(item["scenario_id"]): item for item in scenarios}


def test_audit_distinguishes_teacher_order_from_game_feasibility() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)

    payload = audit_qualified_skill_order(registry)
    by_id = _by_id(payload)

    assert payload["test_scenarios_opened"] == 0
    assert payload["private_captures_opened"] == 0
    assert "not impossible cartridge states" in str(payload["claim"])

    assert "red-strategic-scenario-v2-019-validation" not in by_id

    scenario_017 = by_id["red-strategic-scenario-v2-017-train"]
    assert scenario_017["partition"] == "train"
    assert scenario_017["current_qualified_skill_blockers"] == [
        {
            "objective_id": "defeat_koga",
            "required_but_absent_objective_ids": [],
            "required_any_of_absent_objective_ids": ["obtain_strength", "obtain_surf"],
            "reason": (
                "The qualified Koga chapter requires either the Surf moveset or "
                "the Strength-before-Surf moveset."
            ),
        },
    ]

    assert "red-strategic-scenario-v2-023-validation" not in by_id


def test_audit_finds_early_erika_and_early_cinnabar_curriculum_gaps() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    by_id = _by_id(audit_qualified_skill_order(registry))

    for scenario_id in (
        "red-strategic-scenario-v2-009-train",
        "red-strategic-scenario-v2-010-train",
        "red-strategic-scenario-v2-014-train",
    ):
        assert scenario_id not in by_id

    assert by_id["red-strategic-scenario-v2-041-train"]["current_qualified_skill_blockers"] == [
        {
            "objective_id": "reach_cinnabar",
            "required_but_absent_objective_ids": ["defeat_sabrina"],
            "reason": (
                "The qualified Cinnabar chapter starts from the post-Sabrina "
                "Saffron boundary and uses that route's Fly preparation."
            ),
        }
    ]


def test_contract_rejects_unknown_self_and_empty_prerequisites() -> None:
    with pytest.raises(ValueError, match="objective is unknown"):
        QualifiedSkillOrderContract("unknown", frozenset({"power_on"}), "reason")
    with pytest.raises(ValueError, match="prerequisites are invalid"):
        QualifiedSkillOrderContract("defeat_koga", frozenset(), "reason")
    with pytest.raises(ValueError, match="prerequisites are invalid"):
        QualifiedSkillOrderContract("defeat_koga", frozenset({"defeat_koga"}), "reason")


def test_audit_rejects_duplicate_contract_authority() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    contract = QualifiedSkillOrderContract("defeat_koga", frozenset({"obtain_surf"}), "reason")
    with pytest.raises(ValueError, match="duplicate"):
        audit_qualified_skill_order(registry, contracts=(contract, contract))
