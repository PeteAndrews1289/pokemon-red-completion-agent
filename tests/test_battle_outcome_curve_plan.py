from __future__ import annotations

import json
from pathlib import Path

from pokemon_red_completion.scenario_outcome_adapters import BATTLE_TURN_OBJECTIVE

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-battle-learning-curve-plan-2026-08-14.json"
)


def test_curve_plan_freezes_the_smallest_complete_prefix_design() -> None:
    payload = json.loads(PLAN.read_text(encoding="utf-8"))

    assert payload["schema"] == "pokemon-red-battle-learning-curve-plan-v1"
    assert payload["status"] == "prospective_unmaterialized"
    assert payload["outcome_objective"]["objective_id"] == (
        BATTLE_TURN_OBJECTIVE.objective_id
    )
    assert payload["outcome_objective"]["objective_sha256"] == (
        BATTLE_TURN_OBJECTIVE.objective_sha256
    )
    assert payload["catalog"]["train_contexts"] == 4
    assert payload["catalog"]["development_contexts"] == 4
    assert payload["catalog"]["training_prefix_sizes"] == [1, 2, 4]
    assert payload["catalog"]["required_unique_root_lineages"] == 8
    assert payload["collection"]["replace_after_observing_opponent_or_outcome"] is False
    assert payload["collection"]["repartition_after_observing_outcome"] is False
    assert payload["learner"]["restart_from_same_prior_at_each_prefix"] is True
    assert payload["evaluation"]["inferential_claim"] is False
    assert payload["evaluation"]["promotion_decision"] is False
    assert (
        payload["after_result"][
            "scale_or_stratify_battle_catalog_before_three_family_check"
        ]
        is False
    )
    assert set(payload["protected_access"].values()) == {0}
    assert payload["private_path_fields"] == 0


def test_curve_plan_does_not_embed_a_private_machine_location() -> None:
    encoded = PLAN.read_text(encoding="utf-8")

    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert "file://" not in encoded
