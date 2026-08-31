from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.living_dex_clustered_powered_design import (
    LIVING_DEX_CLUSTERED_POWERED_DESIGN_SCHEMA,
    LIVING_DEX_CLUSTERED_POWERED_ENDPOINT,
    LivingDexClusteredPoweredDesign,
    LivingDexClusteredPoweredDesignError,
    canonical_living_dex_clustered_powered_design_bytes,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = PROJECT_ROOT / "configs" / "living-dex-clustered-powered-design-v2.json"


def test_design_preserves_the_authentic_prefix_and_targets_its_deficits() -> None:
    design = LivingDexClusteredPoweredDesign()
    document = design.public_dict()

    assert design.historical_attempts == 25
    assert design.historical_settled_examples == 18
    assert design.historical_setup_only_attempts == 7
    assert design.prospective_train_attempts == 72
    assert design.maximum_prospective_setup_only_attempts == 30
    assert dict(design.prospective_selected_kind_counts) == {
        LivingDexOptionKind.ACQUIRE: 11,
        LivingDexOptionKind.EVOLVE: 7,
        LivingDexOptionKind.DEVELOP: 9,
        LivingDexOptionKind.MANAGE_STORAGE: 12,
        LivingDexOptionKind.RESUPPLY: 10,
        LivingDexOptionKind.UNLOCK_ACCESS: 11,
        LivingDexOptionKind.EXPLORE: 12,
    }
    assert dict(design.prospective_candidate_position_counts) == {
        0: 24,
        1: 22,
        2: 26,
    }
    assert document["training"]["candidate_position_schedule"][  # type: ignore[index]
        "target_total"
    ] == {"0": 30, "1": 30, "2": 30}
    assert document["training"]["admission"] == (  # type: ignore[index]
        "all_claimed_selected_arm_outcomes_never_outcome_shopped"
    )
    assert document["training"]["teacher_actions_are_labels"] is False  # type: ignore[index]
    assert document["training"]["unselected_actions_are_targets"] is False  # type: ignore[index]


def test_train_siblings_are_bounded_weighted_and_do_not_certify_power() -> None:
    design = LivingDexClusteredPoweredDesign()
    document = design.public_dict()

    assert design.prospective_train_lineages == 36
    assert design.maximum_train_attempts_per_lineage == 2
    assert design.minimum_distinct_settled_train_lineages == 50
    assert document["training"]["cluster_weighting"] == (  # type: ignore[index]
        "equal_total_fit_weight_per_lineage"
    )
    assert document["training"]["upstream_lineage_cross_partition_overlap"] == 0  # type: ignore[index]
    assert document["evaluation"][  # type: ignore[index]
        "within_lineage_siblings_count_toward_primary_endpoint"
    ] is False
    assert document["training"]["behavior_policy"] == (  # type: ignore[index]
        "blocked_random_permutation_full_support_uniform_marginal_v2"
    )
    assert document["training"]["minimum_semantic_families"] == 18  # type: ignore[index]
    assert document["training"]["minimum_menu_templates"] == 10  # type: ignore[index]
    assert document["training"]["minimum_locations"] == 5  # type: ignore[index]
    assert document["training"]["minimum_pressure_values_per_axis"] == 3  # type: ignore[index]


def test_feature_contract_preserves_the_reachable_red_projection() -> None:
    feature = LivingDexClusteredPoweredDesign().public_dict()["feature_contract"]

    assert feature["feature_count"] == 24  # type: ignore[index]
    assert feature["outcome_head_count"] == 9  # type: ignore[index]
    assert feature["minimum_reachable_red_feature_rank"] == 16  # type: ignore[index]
    assert feature["red_trade_rows_fabricated"] == 0  # type: ignore[index]
    assert feature["all_candidate_feature_rows_must_be_supported"] is True  # type: ignore[index]
    assert set(feature["red_direct_option_kinds"]) == {  # type: ignore[index]
        "acquire",
        "develop",
        "evolve",
        "explore",
        "manage_storage",
        "resupply",
        "unlock_access",
    }


def test_development_power_uses_one_independent_endpoint_per_lineage() -> None:
    design = LivingDexClusteredPoweredDesign()
    evaluation = design.public_dict()["evaluation"]

    assert design.k_min_without_forced_losses == 67
    assert design.k_min_with_forced_losses == 100
    assert design.development_lineages == 100
    assert design.confirmatory_questions_per_development_lineage == 1
    assert design.previous_development_power == pytest.approx(0.7996299998823)
    assert design.worst_case_development_power == pytest.approx(
        0.8053956642931617
    )
    assert evaluation["endpoint"] == LIVING_DEX_CLUSTERED_POWERED_ENDPOINT  # type: ignore[index]
    assert evaluation["incompletes_above_budget_rule"] == (  # type: ignore[index]
        "declare_endpoint_underpowered_close_without_promotion"
    )
    assert evaluation["primary_unit"] == (  # type: ignore[index]
        "authenticated_upstream_episode_lineage"
    )
    assert evaluation["focus_kind_schedule"] == {  # type: ignore[index]
        "acquire": 15,
        "develop": 14,
        "evolve": 15,
        "explore": 14,
        "manage_storage": 14,
        "resupply": 14,
        "unlock_access": 14,
    }
    assert evaluation["focus_position_schedule"] == {"0": 34, "1": 33, "2": 33}  # type: ignore[index]
    assert evaluation["minimum_available_candidates_per_question"] == 3  # type: ignore[index]
    assert evaluation["minimum_semantic_families"] == 12  # type: ignore[index]
    assert evaluation["minimum_menu_templates"] == 5  # type: ignore[index]
    assert evaluation["minimum_locations"] == 5  # type: ignore[index]
    assert evaluation["minimum_pressure_values_per_axis"] == 2  # type: ignore[index]
    assert evaluation["policy_branches_per_question"] == 4  # type: ignore[index]
    assert evaluation["same_reset_and_rng_for_every_branch"] is True  # type: ignore[index]
    sensitivity = evaluation["correlation_sensitivity"]  # type: ignore[index]
    assert [point["assumed_intracluster_correlation"] for point in sensitivity] == [
        0.0,
        0.25,
        0.5,
        0.75,
        1.0,
    ]
    assert {point["design_effect"] for point in sensitivity} == {1.0}
    assert {point["effective_independent_lineages"] for point in sensitivity} == {
        100
    }
    assert {point["worst_case_power"] for point in sensitivity} == {
        design.worst_case_development_power
    }


def test_finite_capacity_and_candidate_cap_are_explicitly_unproven() -> None:
    design = LivingDexClusteredPoweredDesign()
    document = design.public_dict()
    capacity = document["capacity"]

    assert design.required_new_lineage_supply == 139
    assert design.maximum_model_candidates == 1
    assert capacity["prospective_train_lineages"] == 36  # type: ignore[index]
    assert capacity["development_lineages"] == 100  # type: ignore[index]
    assert capacity["contingency_lineages"] == 3  # type: ignore[index]
    assert capacity["private_capacity_proven"] is False  # type: ignore[index]
    assert capacity["contingency_use_rule"].startswith(  # type: ignore[index]
        "replace_only_a_pre_branch_unread_invalid_lineage"
    )
    assert document["status"] == "design_only_private_capacity_unproven"


def test_crystal_boundary_penalizes_supported_abstention_and_names_new_mechanics() -> None:
    transfer = LivingDexClusteredPoweredDesign().public_dict()["transfer_boundary"]

    assert transfer["crystal_supported_abstention_score"] == "failure"  # type: ignore[index]
    assert transfer["prospectively_unsupported_mechanic_abstention"] == (  # type: ignore[index]
        "correct_boundary_classification_not_completion_credit"
    )
    vocabulary = set(transfer["capability_vocabulary_required_before_classification"])  # type: ignore[index]
    assert {
        "gender_constraints",
        "happiness_and_friendship_evolution",
        "held_item_acquire_equip_and_consume_workflow",
        "phone_contacts_and_calls",
        "renewable_berry_state",
        "roaming_legendaries",
        "weekly_and_calendar_events",
    } <= vocabulary
    assert transfer["crystal_supported_scope_requires"] == [  # type: ignore[index]
        "frozen_red_model_beats_best_of_three_control_envelope",
        "frozen_red_initialization_beats_zero_initialization",
    ]
    assert transfer["version_trade_event_catalog_scope"] == (  # type: ignore[index]
        "complete_per_title_target_catalog_red_151_crystal_251_and_future_"
        "declared_totals_with_solo_graph_as_a_subplan"
    )
    assert transfer["unsupported_mechanics_receive_gameplay_authority"] is False  # type: ignore[index]
    assert transfer["crystal_adaptation_is_separate_from_zero_shot"] is True  # type: ignore[index]
    assert transfer["red_unseen_kind_coefficients"] == {"trade": 0.0}  # type: ignore[index]
    assert transfer["powered_transfer_plan_required_before_crystal_execution"] is True  # type: ignore[index]
    assert transfer["transfer_statistical_status"] == (  # type: ignore[index]
        "unsized_execution_prohibited_until_separate_powered_plan"
    )


def test_canonical_design_is_path_free_digest_bound_and_action_free() -> None:
    payload = canonical_living_dex_clustered_powered_design_bytes()
    document = json.loads(payload)
    design = LivingDexClusteredPoweredDesign()

    assert payload.endswith(b"\n")
    assert document == design.public_dict()
    assert document["schema"] == LIVING_DEX_CLUSTERED_POWERED_DESIGN_SCHEMA
    assert document["design_sha256"] == design.design_sha256
    assert design.design_sha256 == hashlib.sha256(
        json.dumps(
            design.public_dict(include_digest=False),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()
    assert set(document["authorization"].values()) == {False}
    encoded = payload.decode("ascii")
    for forbidden in (
        "/Users/",
        "/Volumes/",
        "lineage_sha256",
        "physical_root_sha256",
        "selected_arm_identity",
        "state_sha256",
    ):
        assert forbidden not in encoded
    configured_rom = os.environ.get("POKEMON_RED_ROM")
    if configured_rom is not None:
        assert configured_rom not in encoded


def test_committed_design_matches_generator_and_check_mode() -> None:
    assert DESIGN_PATH.read_bytes() == canonical_living_dex_clustered_powered_design_bytes()
    subprocess.run(
        [
            sys.executable,
            "scripts/regenerate_living_dex_clustered_powered_design.py",
            "--check",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("maximum_train_attempts_per_lineage", 3),
        ("minimum_total_settled_train_examples", 59),
        ("minimum_distinct_settled_train_lineages", 49),
        ("minimum_settled_train_examples_per_kind", 7),
        ("minimum_distinct_selected_feature_rows", 49),
        ("minimum_selected_feature_rank", 15),
        ("minimum_selected_feature_rank", 17),
        ("minimum_successful_train_examples", 7),
        ("minimum_unsuccessful_train_examples", 7),
        ("minimum_variable_outcome_heads", 4),
        ("minimum_variable_outcome_range", 0.09),
        ("minimum_available_candidates_per_question", 2),
        ("minimum_train_semantic_families", 17),
        ("minimum_development_semantic_families", 11),
        ("minimum_train_menu_templates", 9),
        ("minimum_development_menu_templates", 4),
        ("minimum_train_locations", 4),
        ("minimum_development_locations", 4),
        ("minimum_train_pressure_values_per_axis", 2),
        ("minimum_development_pressure_values_per_axis", 1),
        ("minimum_development_questions_per_supported_kind", 13),
        ("development_lineages", 99),
        ("development_lineages", 101),
        ("confirmatory_questions_per_development_lineage", 2),
        ("maximum_model_candidates", 2),
        ("alpha", 0.10),
        ("target_power", 0.70),
        ("contingency_lineages", 2),
        ("maximum_forced_development_losses", 2),
        ("smallest_useful_win_probability", 0.40),
        ("smallest_useful_loss_probability", 0.15),
    ),
)
def test_design_rejects_weaker_information_or_independence_mutations(
    field: str,
    value: int | float,
) -> None:
    with pytest.raises(LivingDexClusteredPoweredDesignError):
        replace(LivingDexClusteredPoweredDesign(), **{field: value})


def test_design_rejects_mutated_prefix_or_schedule_totals() -> None:
    design = LivingDexClusteredPoweredDesign()
    kinds = list(design.prospective_selected_kind_counts)
    kinds[0] = (kinds[0][0], kinds[0][1] - 1)
    positions = list(design.prospective_candidate_position_counts)
    positions[0] = (positions[0][0], positions[0][1] - 1)
    development_kinds = list(design.development_focus_kind_counts)
    development_kinds[0] = (
        development_kinds[0][0],
        development_kinds[0][1] - 1,
    )
    development_positions = list(design.development_focus_position_counts)
    development_positions[0] = (
        development_positions[0][0],
        development_positions[0][1] - 1,
    )

    with pytest.raises(LivingDexClusteredPoweredDesignError, match="prefix"):
        replace(design, historical_settled_examples=17)
    with pytest.raises(LivingDexClusteredPoweredDesignError, match="kind"):
        replace(design, prospective_selected_kind_counts=tuple(kinds))
    with pytest.raises(LivingDexClusteredPoweredDesignError, match="position"):
        replace(design, prospective_candidate_position_counts=tuple(positions))
    with pytest.raises(LivingDexClusteredPoweredDesignError, match="focus-kind"):
        replace(design, development_focus_kind_counts=tuple(development_kinds))
    with pytest.raises(LivingDexClusteredPoweredDesignError, match="focus-position"):
        replace(
            design,
            development_focus_position_counts=tuple(development_positions),
        )


def test_design_rejects_a_thinned_review_grid_or_transfer_vocabulary() -> None:
    design = LivingDexClusteredPoweredDesign()

    with pytest.raises(LivingDexClusteredPoweredDesignError, match="correlation"):
        replace(design, correlation_sensitivity_grid=(0.0, 1.0))
    with pytest.raises(LivingDexClusteredPoweredDesignError, match="vocabulary"):
        replace(
            design,
            crystal_capability_vocabulary=design.crystal_capability_vocabulary[:-1],
        )
